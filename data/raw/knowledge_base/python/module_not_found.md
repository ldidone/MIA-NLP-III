# ModuleNotFoundError / ImportError: missing Python library

## Symptom

When running a Python script you see an error such as:

```text
ModuleNotFoundError: No module named 'pandas'
ModuleNotFoundError: No module named 'cv2'
ImportError: No module named sklearn
```

These errors mean Python could not find the requested module in the current
environment. The most common cause is that the package providing that module is
**not installed** in the active interpreter/virtual environment.

## Diagnosis

1. Read the module name from the error message. It is the value after
   `No module named` (e.g. `cv2`, `pandas`, `sklearn`).
2. The **import name** is not always the same as the **pip package name**.
   For example, `import cv2` is provided by the pip package `opencv-python`.
   See `package_name_mapping.md` for common mappings.
3. Confirm which interpreter is running with `python -c "import sys; print(sys.executable)"`.
   Installing into a different interpreter than the one running the code is a
   frequent source of "still not found" confusion.

## Recommended fix

1. Identify the correct pip package name for the missing module.
2. Install it into the **same interpreter** that runs your code:

   ```bash
   python -m pip install <package_name>
   ```

   Always use `python -m pip` (not a bare `pip`) so the package goes into the
   interpreter you are actually using.
3. Verify the import works:

   ```bash
   python -c "import <module_name>"
   ```

## Notes

- Installing packages changes your environment and therefore requires user
  approval before it is performed automatically.
- If the install succeeds but the import still fails, you are likely running a
  different interpreter than the one you installed into.
