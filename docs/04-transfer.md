# Getting files onto the calculators

Neither handheld appears as a USB drive. Both need TI's own free
software. There is no way around this on Windows with a stock device.

## TI-84 Plus CE

**Software:** TI Connect™ CE (free, Windows and Mac, from
education.ti.com).
**Cable:** USB A to mini-B — the one that came with the calculator.

1. Connect the calculator and turn it on.
2. Open TI Connect CE → **Calculator Explorer**.
3. Drag `ti84/dist/QUADFORM.8xp` into the window.
4. On the calculator: `PRGM` → pick it → `ENTER` → `ENTER`.

To go the other way (which you should do once, before writing anything —
see `00-START-HERE.md`), drag the program *out* of Calculator Explorer
onto your desktop, then:

```bash
python tools/inspect_file.py ~/Desktop/MYPROG.8xp
```

**Archived programs do not run.** If a program shows with a `*` in
Calculator Explorer or `ERR:ARCHIVED` on the handheld, unarchive it:
`2ND` `MEM` → `Mem Management` → `Prgm` → select → `ENTER`.

## TI-Nspire CX II

**Software:** TI-Nspire™ CX Student Software, or the smaller TI-Nspire™
CX Computer Link Software (both from education.ti.com).
**Cable:** USB A to mini-B.

1. Connect and turn on the handheld.
2. Open the software → **Content Explorer** (Student Software) or the
   handheld's file tree (Computer Link).
3. Drag `nspire/dist/quadratic.tns` into **My Documents**.
4. On the handheld: open the document. The Python page runs on open, or
   with `ctrl` `R`.

### Modules go somewhere else

A `lib_` module must land in the handheld's **PyLib** folder, not in My
Documents alongside your programs:

```
My Documents/
  PyLib/
    solve.tns          <- from nspire/dist/PyLib/
  quadratic.tns        <- from nspire/dist/
```

Create `PyLib` at the top level of My Documents if it does not exist —
the exact name matters. If an import still fails after copying, close and
reopen the document, or restart the handheld; the module list is not
always rescanned live.

The document name is the module name. `solve.tns` is `import solve`.
Renaming the file renames the module.

## Exam mode — read this before relying on any of it

Both platforms have a lockdown mode (Press-to-Test) that proctors use.

- **TI-84 CE:** entering Press-to-Test disables existing programs and
  applications. They are restored when the mode is exited. Anything
  created *during* test mode is deleted on exit.
- **TI-Nspire:** Press-to-Test restricts documents and features, and
  Python can be among the things disabled depending on the settings the
  proctor chooses.

Treat anything you write here as **unavailable in a proctored exam**
unless you have confirmed otherwise with whoever is running it. Assume
it will be disabled, and check the rules of the specific exam — some
boards ban programmable memory contents outright.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Calculator not detected | Charge cable, not a data cable. Try another. |
| `ERR:ARCHIVED` | Unarchive it (above). |
| Program missing from `PRGM` | It transferred as a different variable type, or the name collided with an existing one. |
| `.tns` opens but the page is blank | It went in as a program document when you wanted a module, or vice versa. |
| Nspire import fails | Wrong folder, wrong document name, or a program document sitting in `PyLib`. |
| Transfer resets the handheld | Source over the size limit — the build warns, do not override it. |
