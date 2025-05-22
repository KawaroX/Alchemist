import sys
from setuptools import setup

APP = ['pdf_converter_gui.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'app_icon.icns',
    'plist': {
        'CFBundleShortVersionString': '0.1.0',
        'CFBundleVersion': '0.1.0',
        'CFBundleName': 'Alchemist',
        'CFBundleDisplayName': 'Alchemist',
    },
    'includes': ['chardet'],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
