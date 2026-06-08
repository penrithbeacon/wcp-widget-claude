"""
py2app build configuration for WCP Claude Agent menu bar app.

Build: python setup.py py2app
Output: dist/WCP Claude Agent.app
"""

from setuptools import setup

APP = ['menubar_agent.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'icons/app.icns',
    'plist': {
        'CFBundleName': 'WCP Claude Agent',
        'CFBundleDisplayName': 'WCP Claude Agent',
        'CFBundleIdentifier': 'com.penrithbeacon.claude-agent',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': True,  # Menu bar only — no Dock icon
        'LSMinimumSystemVersion': '11.0',
        'NSHighResolutionCapable': True,
    },
    'packages': ['rumps', 'flask', 'jinja2', 'markupsafe', 'werkzeug',
                 'click', 'blinker', 'itsdangerous'],
    'includes': ['agent', 'config'],
    'resources': ['icons/menubar.png', 'icons/menubar@2x.png'],
}

setup(
    app=APP,
    name='WCP Claude Agent',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
