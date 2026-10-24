#!/usr/bin/env python
"""Command-line entry point for Django checks, migrations and academy management tasks."""
import os
import sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.core.management import execute_from_command_line
execute_from_command_line(sys.argv)
