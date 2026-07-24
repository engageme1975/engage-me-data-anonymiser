from distutils.core import setup

import py2exe


setup(
    windows=["desktop_app.py"],
    options={
        "py2exe": {
            "compressed": True,
            "bundle_files": 1,
            "includes": [
                "tkinter",
                "pandas",
                "openpyxl",
                "presidio_analyzer",
                "presidio_anonymizer",
                "spacy",
                "beyond_recognizers",
                "anonymization_core",
            ],
            "packages": [
                "pandas",
                "openpyxl",
                "presidio_analyzer",
                "presidio_anonymizer",
                "spacy",
            ],
        }
    },
    zipfile=None,
)
