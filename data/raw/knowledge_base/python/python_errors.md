# Python Syntax and Runtime Errors

This document provides symptoms, examples, and recommended fixes for common Python runtime and syntax errors.

---

## Syntax Error

### Symptom
When code violates Python's grammar rules, the interpreter cannot parse the code and raises a `SyntaxError`.

### Example
```python
if x = 10
    print("Hello")
```
*Note: In this example, the assignment operator `=` is used instead of the comparison operator `==`, and the colon `:` is missing at the end of the `if` statement.*

### Recommended fix
Check the grammar of the code. In Python:
- Conditions in control flow statements (`if`, `elif`, `while`) must use the equality operator `==` for comparisons (not the assignment operator `=`).
- Statements defining a block of code (such as `if`, `else`, `elif`, `for`, `while`, `def`, `class`) must end with a colon `:`.

---

## Indentation Error

### Symptom
Python uses whitespace to define code blocks. Inconsistent spacing or missing indentation raises an `IndentationError`.

### Example
```python
def my_function():
print("Missing indent")
```
*Note: The `print` statement inside the function body is not indented.*

### Recommended fix
Ensure all statements belonging to a block (like functions, loops, or conditionals) are indented consistently (normally by 4 spaces).

---

## Name Error

### Symptom
Referencing a variable, function, or class name that has not been defined in the current scope raises a `NameError`.

### Example
```python
message = "Welcome"
print(mesage)  # Typo in variable name
```

### Recommended fix
Check the spelling of the identifier. Ensure the variable or function is defined before you attempt to access it, and that there are no typographical errors.

---

## Type Error

### Symptom
Attempting an operation on incompatible data types (for example, adding a string to an integer) raises a `TypeError`.

### Example
```python
total = "Price: " + 50
```

### Recommended fix
Explicitly convert variables to matching types before performing operations, or use formatted string literals (f-strings) to safely interpolate different types:
```python
# Fix option 1: Explicit conversion
total = "Price: " + str(50)

# Fix option 2: f-string
total = f"Price: {50}"
```

---

## Index Error

### Symptom
Attempting to access an item in a list (or other sequence) using an index that is out of its valid range raises an `IndexError`.

### Example
```python
items = ["apple", "banana"]
print(items[2])  # The maximum index available is 1
```
*Note: Python lists use 0-based indexing. A list with 2 items has valid indices `0` and `1`.*

### Recommended fix
Ensure the index you are trying to access is within the bounds of the list. The valid range of indices for a non-empty list `L` is `0` to `len(L) - 1` (or `-len(L)` to `-1` for negative indexing).
