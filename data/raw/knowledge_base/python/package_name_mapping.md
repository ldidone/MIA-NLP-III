# Import name to pip package name mapping

The name you use in `import` is not always the name you pass to `pip install`.
Use this table to map a missing module to the correct pip package.

## Common mappings

```text
import sklearn   -> pip install scikit-learn
import cv2       -> pip install opencv-python
import PIL       -> pip install Pillow
import yaml      -> pip install PyYAML
import dotenv    -> pip install python-dotenv
import bs4       -> pip install beautifulsoup4
import skimage   -> pip install scikit-image
import Crypto    -> pip install pycryptodome
import OpenSSL   -> pip install pyOpenSSL
import google    -> pip install google-api-python-client
import psycopg2  -> pip install psycopg2-binary
import fitz      -> pip install PyMuPDF
import win32api  -> pip install pywin32
import serial    -> pip install pyserial
```

## Same-name packages (no mapping needed)

Many libraries use the same name for import and install, for example:

```text
import pandas    -> pip install pandas
import numpy     -> pip install numpy
import requests  -> pip install requests
import flask     -> pip install flask
import torch     -> pip install torch
```

## How to use this mapping

1. Take the module name from `ModuleNotFoundError: No module named '<module>'`.
2. If `<module>` appears on the left-hand side of a mapping above, install the
   package on the right-hand side.
3. Otherwise, try `pip install <module>` directly.
