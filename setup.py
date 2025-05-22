import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="Alchemist",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="A PDF converter application",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your_username/Alchemist",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=[
        'PyPDF2',
        'reportlab',
        'pillow'
    ],
    entry_points={
        'console_scripts': [
            'Alchemist=pdf_converter_gui:main',
        ],
    },
    include_package_data=True,
    options={
        'app': {
            'formal_name': 'Alchemist',
            'bundle_name': 'Alchemist',
        }
    },
    data_files=[
        ('resources', ['app_icon.icns', 'icon.ico']),
    ],
)
