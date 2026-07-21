"""writ.session: implementation modules behind the bin/lib/writ-session.py facade.

POL-6 splits the 3173-line writ-session.py god-module into cohesive submodules here.
The facade re-exports their public surface and keeps main(), so the three load paths
(hook CLI, server spec_from_file_location, the test path loaders) keep working unchanged.
"""
