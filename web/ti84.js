/* A TI-84 Plus CE interpreter, ported from tools/simulate_84.py.
 *
 * There are deliberately two implementations. The Python one is the
 * reference -- it shares its scanner with the builder, so it sees exactly
 * the token stream that gets written into the .8xp. This one exists so the
 * browser can run a program interactively, and web/test_ti84.mjs checks the
 * two agree on a fixed set of programs. If they ever disagree, the Python
 * one is right.
 *
 * Execution is a generator. TI-BASIC blocks on Prompt, Input, Menu( and
 * Pause; a browser cannot block, so the interpreter yields a request and
 * the caller resumes it with the answer. That also gives single-stepping
 * for free.
 *
 * Runs in node (module.exports) and in the browser (window.TI84).
 */
(function (root) {
  "use strict";

  var COLS = 26, ROWS = 10;
  var NARROW_COLS = 16, NARROW_ROWS = 8;
  var SEPARATORS = { 0x3f: 1, 0x3e: 1 };
  var OPENERS = { "Then": 1, "For(": 1, "While ": 1, "Repeat ": 1 };
  var LOWER = "abcdefghijklmnopqrstuvwxyz";
  var LABEL_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789θ";
  var VARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZθ";

  /* ---- errors ---------------------------------------------------- */

  function TIError(name, detail) {
    this.name = name;
    this.detail = detail || "";
    this.message = "ERR:" + name + (detail ? "  (" + detail + ")" : "");
  }
  TIError.prototype = Object.create(Error.prototype);

  function Unsupported(message) {
    this.name = "Unsupported";
    this.message = message;
  }
  Unsupported.prototype = Object.create(Error.prototype);

  /* ---- ►Frac ----------------------------------------------------- */

  /* Tagged so Disp still right-aligns it: on screen it is a number, even
   * though it is carried as text. */
  function Frac(text) { this.text = text; }
  Frac.prototype.toString = function () { return this.text; };

  function toFrac(value) {
    if (typeof value !== "number") return value;
    // Stern-Brocot search, stopping at the denominator the handheld
    // stops at. Past that it gives up and leaves the decimal, and
    // reproducing the giving up is the point: a root shown as
    // .3333333333 is how you learn your arithmetic went through a float.
    var sign = value < 0 ? -1 : 1, x = Math.abs(value);
    var lo = [0, 1], hi = [1, 0], best = null;
    for (var i = 0; i < 64; i++) {
      var mid = [lo[0] + hi[0], lo[1] + hi[1]];
      if (mid[1] > 9999) break;
      var v = mid[0] / mid[1];
      if (Math.abs(v - x) < 1e-9) { best = mid; break; }
      if (v < x) lo = mid; else hi = mid;
    }
    if (!best) return value;
    if (best[1] === 1) return sign * best[0];
    return new Frac((sign * best[0]) + "/" + best[1]);
  }

  function canonical(body, scanner) {
    return scanner.scan(body).map(function (t) { return scanner.display(t.text); }).join("");
  }

  /* ---- number formatting ----------------------------------------- */

  function tiStr(value) {
    if (value instanceof Frac) return value.text;
    if (typeof value === "string") return value;
    if (value !== value) return "NAN";
    if (value === Infinity || value === -Infinity) return "INF";

    var text;
    if (value === Math.trunc(value) && Math.abs(value) < 1e10) {
      text = String(Math.trunc(value));
    } else {
      text = significant(value, 10);
      if (text.indexOf("e") >= 0) {
        var parts = text.split("e");
        return parts[0] + "E" + parseInt(parts[1], 10);
      }
    }
    // TI drops the leading zero: .5, never 0.5
    if (text.indexOf("0.") === 0) text = text.slice(1);
    else if (text.indexOf("-0.") === 0) text = "-" + text.slice(2);
    return text;
  }

  function significant(value, digits) {
    var text = value.toPrecision(digits);
    if (text.indexOf("e") < 0 && text.indexOf(".") >= 0) {
      text = text.replace(/0+$/, "").replace(/\.$/, "");
    }
    return text;
  }

  /* ---- screen ----------------------------------------------------- */

  function Screen(cols, rows) {
    this.cols = cols || COLS;
    this.rows = rows || ROWS;
    this.truncated = [];
    this.clear();
  }
  Screen.prototype.clear = function () {
    this.grid = [];
    for (var r = 0; r < this.rows; r++) this.grid.push(new Array(this.cols).fill(" "));
    this.cursor = 0;
  };
  Screen.prototype.scroll = function () {
    this.grid.shift();
    this.grid.push(new Array(this.cols).fill(" "));
    this.cursor = this.rows - 1;
  };
  Screen.prototype.write = function (text, row, col, right) {
    col = col || 0;
    if (row === null || row === undefined) {
      if (this.cursor >= this.rows) this.scroll();
      row = this.cursor;
      this.cursor += 1;
    }
    if (text.length > this.cols - col) {
      this.truncated.push(text);
      text = text.slice(0, this.cols - col);
    }
    if (right) col = Math.max(0, this.cols - text.length);
    for (var i = 0; i < text.length; i++) {
      if (col + i >= 0 && col + i < this.cols) this.grid[row][col + i] = text[i];
    }
  };
  Screen.prototype.lines = function () {
    return this.grid.map(function (row) { return row.join(""); });
  };

  /* ---- scanner ---------------------------------------------------- */

  function isAscii(text) { return !/[^\x00-\x7F]/.test(text); }

  function nicer(a, b) {
    if (isAscii(a) !== isAscii(b)) return isAscii(b);   // glyph beats ASCII
    return a.length < b.length;
  }

  function Scanner(table) {
    this.table = table;
    this.maxlen = 0;
    // bits -> the spelling to show a human. `^^2` and `²` are both 0x0D;
    // the ASCII one exists so you can type it, the calculator draws the
    // glyph. Anything shown to a person wants the glyph.
    this.display_ = {};
    for (var name in table) {
      if (name.length > this.maxlen) this.maxlen = name.length;
      var bits = table[name];
      var current = this.display_[bits];
      if (current === undefined || nicer(name, current)) this.display_[bits] = name;
    }
  }
  Scanner.prototype.display = function (name) {
    if (!this.has(name)) return name;
    var chosen = this.display_[this.table[name]];
    return chosen === undefined ? name : chosen;
  };
  Scanner.prototype.has = function (name) {
    return Object.prototype.hasOwnProperty.call(this.table, name);
  };
  Scanner.prototype.bits = function (name) {
    return this.has(name) ? this.table[name] : "";
  };
  Scanner.prototype.byte = function (name) {
    var hex = this.bits(name);
    return hex.length === 2 ? parseInt(hex, 16) : -1;
  };
  Scanner.prototype.scan = function (text) {
    var out = [], i = 0, line = 1, col = 1, n = text.length;
    while (i < n) {
      var ch = text[i];
      if (ch === "\n") {
        out.push({ kind: "tok", text: "\n", line: line, col: col });
        i++; line++; col = 1;
        continue;
      }
      if (ch === '"') {
        // A string runs to the next quote or to end of line: TI closes an
        // unterminated string at the newline, so a missing quote is legal.
        var j = i + 1;
        while (j < n && text[j] !== '"' && text[j] !== "\n") j++;
        var end = (j < n && text[j] === '"') ? j + 1 : j;
        out.push({ kind: "str", text: text.slice(i, end), line: line, col: col });
        col += end - i; i = end;
        continue;
      }
      var matched = false;
      var limit = Math.min(this.maxlen, n - i);
      for (var len = limit; len >= 1; len--) {
        var cand = text.substr(i, len);
        if (cand.indexOf("\n") >= 0) continue;
        if (this.has(cand)) {
          out.push({ kind: "tok", text: cand, line: line, col: col });
          i += len; col += len; matched = true;
          break;
        }
      }
      if (!matched) {
        out.push({ kind: "unk", text: ch, line: line, col: col });
        i++; col++;
      }
    }
    return out;
  };

  /* ---- preprocess ------------------------------------------------- */

  function preprocess(text, scanner) {
    var lines = text.replace(/\r\n/g, "\n").split("\n");
    var out = [], map = [];
    for (var n = 0; n < lines.length; n++) {
      var raw = lines[n];
      if (/^\s*\/\//.test(raw)) continue;
      var line = raw.trim();
      if (!line) continue;
      out.push(restoreBareCommand(line, scanner));
      map.push(n + 1);
    }
    return { text: out.join("\n") + "\n", map: map };
  }

  /* Most token names carry their trailing space: the token is `Pause `,
   * not `Pause`. Stripping indentation also strips that space, so a bare
   * Pause would scan as P, a, u, s, e. Put it back. */
  function restoreBareCommand(line, scanner) {
    var match = /([A-Za-z]+)$/.exec(line);
    if (!match) return line;
    var word = match[1];
    if (!scanner.has(word) && scanner.has(word + " ")) return line + " ";
    return line;
  }

  /* ---- statements ------------------------------------------------- */

  function splitStatements(tokens, scanner) {
    var statements = [], current = [];
    for (var i = 0; i < tokens.length; i++) {
      var t = tokens[i];
      if (t.kind === "tok" && SEPARATORS[scanner.byte(t.text)]) {
        statements.push(current); current = [];
      } else {
        current.push(t);
      }
    }
    statements.push(current);
    return statements.filter(function (s) { return s.length > 0; });
  }

  function matchBlocks(statements) {
    var ends = {}, elses = {}, stack = [];
    for (var i = 0; i < statements.length; i++) {
      var head = statements[i][0].text;
      if (OPENERS[head]) stack.push(i);
      else if (head === "Else") {
        if (!stack.length) throw new TIError("SYNTAX", "Else with no If");
        elses[stack[stack.length - 1]] = i;
      } else if (head === "End") {
        if (!stack.length) throw new TIError("SYNTAX", "End with no open block");
        ends[stack.pop()] = i;
      }
    }
    if (stack.length) throw new TIError("SYNTAX", "unclosed block");
    return { ends: ends, elses: elses };
  }

  /* ---- expressions ------------------------------------------------ */

  function Parser(tokens, machine) {
    this.tokens = tokens; this.machine = machine; this.pos = 0;
  }
  Parser.prototype.peek = function () { return this.tokens[this.pos] || null; };
  Parser.prototype.name = function () { var t = this.peek(); return t ? t.text : null; };
  Parser.prototype.take = function () { return this.tokens[this.pos++]; };
  Parser.prototype.atEnd = function () { return this.pos >= this.tokens.length; };
  Parser.prototype.accept = function () {
    var here = this.name();
    for (var i = 0; i < arguments.length; i++) {
      if (here === arguments[i]) { this.pos++; return here; }
    }
    return null;
  };
  Parser.prototype.num = function (value, where) {
    if (typeof value === "string" || value instanceof Frac) {
      throw new TIError("DATA TYPE", where + " got text");
    }
    return value;
  };

  Parser.prototype.expr = function () {
    var left = this.andExpr(), op;
    while ((op = this.accept(" or ", " xor ")) !== null) {
      var right = this.andExpr();
      left = op === " or " ? (left || right ? 1 : 0) : ((!!left !== !!right) ? 1 : 0);
    }
    return left;
  };
  Parser.prototype.andExpr = function () {
    var left = this.rel();
    while (this.accept(" and ") !== null) left = (left && this.rel()) ? 1 : 0;
    return left;
  };
  Parser.prototype.rel = function () {
    var left = this.add(), op;
    while ((op = this.accept("=", "<", ">", "<=", "≤", ">=", "≥", "!=", "≠")) !== null) {
      var right = this.add();
      if (op === "=") left = left === right ? 1 : 0;
      else if (op === "<") left = left < right ? 1 : 0;
      else if (op === ">") left = left > right ? 1 : 0;
      else if (op === "<=" || op === "≤") left = left <= right ? 1 : 0;
      else if (op === ">=" || op === "≥") left = left >= right ? 1 : 0;
      else left = left !== right ? 1 : 0;
    }
    return left;
  };
  Parser.prototype.add = function () {
    var left = this.mul(), op;
    while ((op = this.accept("+", "-")) !== null) {
      var right = this.mul();
      if (op === "+") {
        var ls = typeof left === "string", rs = typeof right === "string";
        if (ls || rs) {
          if (!(ls && rs)) throw new TIError("DATA TYPE", "string + number");
          left = left + right;
        } else left = left + right;
      } else {
        left = this.num(left, "-") - this.num(right, "-");
      }
    }
    return left;
  };
  Parser.prototype.mul = function () {
    var left = this.unary(), op;
    for (;;) {
      op = this.accept("*", "/");
      if (op !== null) {
        var right = this.unary();
        if (op === "*") left = this.num(left, "*") * this.num(right, "*");
        else {
          if (this.num(right, "/") === 0) throw new TIError("DIVIDE BY 0");
          left = this.num(left, "/") / right;
        }
        continue;
      }
      // Implicit multiplication: 2A, 2(X+1), A(B+C). Also where a
      // mistyped ALL-CAPS command lands -- MENU( scans as M*E*N*U*(...).
      if (this.startsValue()) {
        // Guard: if the factor consumed no tokens we would spin here
        // forever. Turn that into a diagnosable error rather than a hang.
        var before = this.pos;
        var factor = this.unary();
        if (this.pos === before) {
          throw new Unsupported(
            "parser made no progress at " + JSON.stringify(this.name()));
        }
        left = this.num(left, "implicit *") * this.num(factor, "implicit *");
        continue;
      }
      return left;
    }
  };
  Parser.prototype.startsValue = function () {
    var t = this.peek();
    if (!t || t.kind === "str") return false;
    var text = t.text;
    if (text === "(") return true;
    if (text.length === 1 && (/[0-9]/.test(text) || VARS.indexOf(text) >= 0)) return true;
    if (text === "pi" || text === "π" || text === "e" || text === "Ans" || text === "rand") return true;
    return text.length > 1 && text.slice(-1) === "(";
  };
  Parser.prototype.unary = function () {
    if (this.accept("~", "⁻", "|-") !== null) return -this.num(this.unary(), "negation");
    return this.power();
  };
  Parser.prototype.power = function () {
    var base = this.atom();
    if (this.accept("^") !== null) base = Math.pow(this.num(base, "^"), this.num(this.unary(), "^"));
    else if (this.accept("²", "^^2") !== null) base = Math.pow(this.num(base, "squared"), 2);
    for (;;) {
      if (this.accept("►Frac", ">Frac") !== null) base = toFrac(base);
      else if (this.accept("►Dec", ">Dec") !== null) base = (base instanceof Frac) ? Number(base.text.split("/")[0]) / Number(base.text.split("/")[1]) : base;
      else return base;
    }
  };
  Parser.prototype.atom = function () {
    var t = this.peek();
    if (!t) throw new TIError("SYNTAX", "expression ended early");
    var text = t.text;

    if (t.kind === "str") {
      this.take();
      // A TI string is tokens, not characters, so the ASCII stand-ins
      // resolve inside a literal too: `^^2` really is the squared token
      // and the handheld draws a superscript 2. Print the raw source and
      // you would believe your title says Y=AX^^2+BX+C.
      return canonical(text.replace(/"/g, ""), this.machine.scanner);
    }
    if (text === "(") {
      this.take();
      var value = this.expr();
      this.accept(")");            // closing paren optional, as on TI
      return value;
    }
    // ANCHORED. Unanchored, this matches any multi-character token that
    // happens to contain a digit -- `cos^-1(`, `10^(` -- which routes a
    // function into the number parser, consumes nothing, and hangs the
    // implicit-multiplication loop below. Python's .isdigit() is false
    // for those, which is why only this port had the bug.
    if (/^[0-9]$/.test(text) || text === ".") return this.number();
    if (text.length > 1 && text.slice(-1) === "(") return this.call();
    if (text === "pi" || text === "π") { this.take(); return Math.PI; }
    if (text === "e") { this.take(); return Math.E; }
    if (text === "Ans") { this.take(); return this.machine.ans; }
    if (text.indexOf("Str") === 0) { this.take(); return this.machine.strings[text] || ""; }
    if (text.length === 1 && VARS.indexOf(text) >= 0) {
      this.take();
      return this.machine.vars[text] || 0;
    }
    throw new Unsupported("cannot evaluate token " + JSON.stringify(text));
  };
  Parser.prototype.number = function () {
    var digits = "";
    while (!this.atEnd()) {
      var text = this.name();
      if (text !== null && (/^[0-9]$/.test(text) || text === ".")) digits += this.take().text;
      else break;
    }
    return digits ? parseFloat(digits) : 0;
  };
  Parser.prototype.call = function () {
    var fn = this.take().text, args = [];
    if (!this.atEnd() && this.name() !== ")") {
      args.push(this.expr());
      while (this.accept(",") !== null) args.push(this.expr());
    }
    this.accept(")");
    var a = args.length ? args[0] : 0, m = this.machine;

    switch (fn) {
      case "sqrt(": case "√(":
        if (a < 0) throw new TIError("NONREAL ANS");
        return Math.sqrt(a);
      case "abs(": return Math.abs(a);
      case "int(": return Math.floor(a);
      case "iPart(": return Math.trunc(a);
      case "fPart(": return a - Math.trunc(a);
      case "round(": {
        var d = args.length > 1 ? args[1] : 9;
        var f = Math.pow(10, d);
        return Math.round(a * f) / f;
      }
      case "gcd(": return gcd(Math.abs(Math.trunc(a)), Math.abs(Math.trunc(args[1])));
      case "lcm(": {
        var g = gcd(Math.abs(Math.trunc(a)), Math.abs(Math.trunc(args[1])));
        return g ? Math.abs(Math.trunc(a) * Math.trunc(args[1])) / g : 0;
      }
      case "remainder(": return Math.trunc(a) % Math.trunc(args[1]);
      case "max(": return Math.max(a, args[1]);
      case "min(": return Math.min(a, args[1]);
      case "not(": return a ? 0 : 1;
      case "length(": return String(a).length;
      case "sub(": return String(a).substr(args[1] - 1, args[2]);
      case "inString(": return String(a).indexOf(String(args[1]), args.length > 2 ? args[2] - 1 : 0) + 1;
      case "toString(": return tiStr(a);
      case "sin(": return Math.sin(m.degrees ? a * Math.PI / 180 : a);
      case "cos(": return Math.cos(m.degrees ? a * Math.PI / 180 : a);
      case "tan(": return Math.tan(m.degrees ? a * Math.PI / 180 : a);
      case "sin^-1(": case "asin(": case "arcsin(": case "sin⁻¹(":
        return degIf(m, Math.asin(a));
      case "cos^-1(": case "acos(": case "arccos(": case "cos⁻¹(":
        return degIf(m, Math.acos(a));
      case "tan^-1(": case "atan(": case "arctan(": case "tan⁻¹(":
        return degIf(m, Math.atan(a));
      case "ln(": return Math.log(a);
      case "log(": return Math.log10(a);
      case "e^(": return Math.exp(a);
      case "10^(": return Math.pow(10, a);
    }
    throw new Unsupported("function " + fn + " is not implemented");
  };
  function degIf(machine, radians) {
    return machine.degrees ? radians * 180 / Math.PI : radians;
  }
  function gcd(a, b) { while (b) { var t = b; b = a % b; a = t; } return a; }

  /* ---- machine ---------------------------------------------------- */

  function Machine(scanner, screen) {
    this.scanner = scanner;
    this.screen = screen;
    this.vars = {};
    this.strings = {};
    this.ans = 0;
    this.degrees = false;
    this.steps = 0;
  }
  Machine.prototype.alignsRight = function (value) {
    return (value instanceof Frac) || typeof value !== "string";
  };
  Machine.prototype.assign = function (name, value) {
    if (name.indexOf("Str") === 0) this.strings[name] = value;
    else this.vars[name] = value;
    this.ans = value;
  };
  Machine.prototype.evaluate = function (tokens) {
    return new Parser(tokens, this).expr();
  };
  Machine.prototype.arglist = function (tokens, wantName) {
    var p = new Parser(tokens, this), args = [];
    if (p.atEnd()) return args;
    if (wantName) { args.push(p.take().text); p.accept(","); }
    args.push(p.expr());
    while (p.accept(",") !== null) args.push(p.expr());
    return args;
  };
  Machine.prototype.labelOf = function (statement) {
    var out = "";
    for (var i = 1; i < statement.length && out.length < 2; i++) {
      var t = statement[i];
      if (t.kind === "tok" && t.text.length === 1 && LABEL_CHARS.indexOf(t.text) >= 0) out += t.text;
      else break;
    }
    return out;
  };
  Machine.prototype.sourceOf = function (statement) {
    return statement.map(function (t) { return t.text; }).join("");
  };

  /* The interpreter. Yields {type:"input"|"pause"|"menu"|"step"} whenever
   * it needs the outside world, and is resumed with the answer. */
  Machine.prototype.run = function* (source, options) {
    options = options || {};
    var pre = preprocess(source, this.scanner);
    var tokens = this.scanner.scan(pre.text);

    for (var t = 0; t < tokens.length; t++) {
      if (tokens[t].kind === "unk") {
        throw new TIError("SYNTAX", "no token matches " + JSON.stringify(tokens[t].text));
      }
    }

    var statements = splitStatements(tokens, this.scanner);
    var blocks = matchBlocks(statements);
    var labels = {};
    for (var i = 0; i < statements.length; i++) {
      if (statements[i][0].text === "Lbl ") labels[this.labelOf(statements[i])] = i;
    }

    var loops = [], pc = 0, machine = this;
    while (pc < statements.length) {
      this.steps++;
      if (this.steps > 200000) throw new TIError("BREAK", "200,000 steps -- probably an infinite loop");

      var statement = statements[pc];
      var head = statement[0].text;
      var origLine = pre.map[statement[0].line - 1] || statement[0].line;

      if (options.step) {
        yield { type: "step", pc: pc, line: origLine, source: this.sourceOf(statement) };
      }

      var next = yield* this.step(statement, head, pc, statements, blocks, labels, loops);
      if (next === null) return;
      pc = next;
    }
  };

  Machine.prototype.step = function* (statement, head, pc, statements, blocks, labels, loops) {
    var rest = statement.slice(1), i, args, value;
    var ends = blocks.ends, elses = blocks.elses;

    if (head === "ClrHome") { this.screen.clear(); return pc + 1; }

    if (head === "Disp ") {
      args = this.arglist(rest);
      for (i = 0; i < args.length; i++) {
        this.screen.write(tiStr(args[i]), null, 0, this.alignsRight(args[i]));
      }
      return pc + 1;
    }

    if (head === "Output(") {
      args = this.arglist(rest);
      this.screen.write(tiStr(args[2]), args[0] - 1, args[1] - 1, false);
      return pc + 1;
    }

    if (head === "Pause ") {
      if (rest.length) {
        args = this.arglist(rest);
        for (i = 0; i < args.length; i++) {
          this.screen.write(tiStr(args[i]), null, 0, this.alignsRight(args[i]));
        }
      }
      yield { type: "pause" };
      return pc + 1;
    }

    if (head === "Prompt ") {
      for (i = 0; i < rest.length; i++) {
        if (rest[i].text === ",") continue;
        var name = rest[i].text;
        var answer = yield { type: "input", prompt: name + "=?", variable: name };
        this.assign(name, parseFloat(answer) || 0);
      }
      return pc + 1;
    }

    if (head === "Input ") {
      var prompt = "?", index = 0;
      if (rest.length && rest[0].kind === "str") {
        prompt = rest[0].text.replace(/"/g, "");
        index = rest.length > 1 ? 2 : 1;
      }
      var target = rest[index] ? rest[index].text : "X";
      var got = yield { type: "input", prompt: prompt, variable: target };
      if (target.indexOf("Str") === 0) this.strings[target] = got;
      else this.assign(target, parseFloat(got) || 0);
      return pc + 1;
    }

    if (head === "If ") {
      var condition = this.evaluate(rest);
      var following = statements[pc + 1];
      if (following && following[0].text === "Then") {
        if (condition) return pc + 2;
        var target2 = elses[pc + 1];
        return target2 !== undefined ? target2 + 1 : ends[pc + 1] + 1;
      }
      return condition ? pc + 1 : pc + 2;
    }

    if (head === "Then") return pc + 1;

    if (head === "Else") return ends[this.openerOf(pc, statements)] + 1;

    if (head === "For(") {
      args = this.arglist(rest, true);
      var vname = args[0], start = args[1], stop = args[2];
      var stepBy = args.length > 3 ? args[3] : 1;
      this.assign(vname, start);
      if ((stepBy > 0 && start > stop) || (stepBy < 0 && start < stop)) return ends[pc] + 1;
      loops.push({ kind: "For(", start: pc, name: vname, stop: stop, step: stepBy });
      return pc + 1;
    }

    if (head === "While ") {
      if (this.evaluate(rest)) {
        loops.push({ kind: "While ", start: pc, cond: rest });
        return pc + 1;
      }
      return ends[pc] + 1;
    }

    if (head === "Repeat ") {
      loops.push({ kind: "Repeat ", start: pc, cond: rest });
      return pc + 1;
    }

    if (head === "End") {
      if (!loops.length) return pc + 1;
      var loop = loops[loops.length - 1];
      if (ends[loop.start] !== pc) return pc + 1;
      if (loop.kind === "For(") {
        this.vars[loop.name] = (this.vars[loop.name] || 0) + loop.step;
        var now = this.vars[loop.name];
        if ((loop.step > 0 && now <= loop.stop) || (loop.step < 0 && now >= loop.stop)) {
          return loop.start + 1;
        }
        loops.pop();
        return pc + 1;
      }
      if (loop.kind === "While ") {
        if (this.evaluate(loop.cond)) return loop.start + 1;
        loops.pop();
        return pc + 1;
      }
      if (this.evaluate(loop.cond)) { loops.pop(); return pc + 1; }  // Repeat exits when TRUE
      return loop.start + 1;
    }

    if (head === "Lbl ") return pc + 1;

    if (head === "Goto ") {
      var label = this.labelOf(statement);
      if (!(label in labels)) throw new TIError("LABEL", "no Lbl " + label);
      loops.length = 0;      // TI leaks here; we simply drop it
      return labels[label];
    }

    if (head === "Stop" || head === "Return") return null;

    if (head === "DelVar ") { delete this.vars[rest[0].text]; return pc + 1; }

    if (head === "Menu(") {
      var options = this.menuOptions(rest);
      var choice = yield { type: "menu", options: options.map(function (o) { return o.text; }) };
      var picked = options[choice];
      if (!picked || !(picked.label in labels)) {
        throw new TIError("LABEL", "no Lbl " + (picked ? picked.label : "?"));
      }
      return labels[picked.label];
    }

    if (head === "Degree" || head === "Radian") {
      this.degrees = head === "Degree";
      return pc + 1;
    }

    if (head === "Wait ") return pc + 1;

    // Not a command, so an expression -- possibly a store.
    var parser = new Parser(statement, this);
    value = parser.expr();
    if (parser.accept("->", "→") !== null) {
      var dest = parser.take().text;
      if (dest.indexOf("Str") === 0) this.strings[dest] = value;
      else this.assign(dest, value);
    } else {
      this.ans = value;
      this.screen.write(tiStr(value), null, 0, this.alignsRight(value));
    }
    return pc + 1;
  };

  Machine.prototype.openerOf = function (pc, statements) {
    var depth = 0;
    for (var i = pc - 1; i >= 0; i--) {
      var head = statements[i][0].text;
      if (head === "End") depth++;
      else if (OPENERS[head]) {
        if (depth === 0) return i;
        depth--;
      }
    }
    throw new TIError("SYNTAX", "Else with no If");
  };

  Machine.prototype.menuOptions = function (rest) {
    var parser = new Parser(rest, this);
    parser.expr();                       // the title
    var options = [];
    while (parser.accept(",") !== null) {
      var text = parser.expr();
      parser.accept(",");
      var label = "";
      // Stop at ")" as well as ",": the last option is followed by the
      // closing paren, and without this only the LAST entry is broken.
      while (!parser.atEnd() && parser.name() !== "," && parser.name() !== ")") {
        label += parser.take().text;
      }
      options.push({ text: String(text), label: label.trim() });
    }
    return options;
  };

  /* ---- driver used by the tests ----------------------------------- */

  function runToCompletion(source, table, inputs, options) {
    options = options || {};
    var scanner = new Scanner(table);
    var screen = new Screen(options.cols, options.rows);
    var machine = new Machine(scanner, screen);
    var queue = (inputs || []).slice();
    var iterator = machine.run(source, {});
    var result = iterator.next(), error = null;

    try {
      while (!result.done) {
        var request = result.value;
        if (request.type === "input") result = iterator.next(queue.shift());
        else if (request.type === "menu") result = iterator.next(parseInt(queue.shift(), 10) - 1);
        else result = iterator.next();
      }
    } catch (err) {
      error = err;
    }
    return { screen: screen, machine: machine, error: error };
  }

  var api = {
    Scanner: Scanner, Screen: Screen, Machine: Machine, Parser: Parser,
    TIError: TIError, Unsupported: Unsupported, Frac: Frac,
    preprocess: preprocess, splitStatements: splitStatements,
    tiStr: tiStr, toFrac: toFrac, runToCompletion: runToCompletion,
    COLS: COLS, ROWS: ROWS, NARROW_COLS: NARROW_COLS, NARROW_ROWS: NARROW_ROWS
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TI84 = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
