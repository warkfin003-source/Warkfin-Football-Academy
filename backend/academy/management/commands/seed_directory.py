import json
from pathlib import Path
from django.core.management.base import BaseCommand
from academy.models import Player, Squad

class Command(BaseCommand):
    help='Import the 28 public directory entries without creating accounts or guessing squad assignments.'
    def handle(self,*args,**options):
        for name in ('Squad A','Squad B'): Squad.objects.get_or_create(name=name)
        entries=json.loads((Path(__file__).resolve().parents[2]/'seed_players.json').read_text())
        created=0
        for entry in entries:
            _,new=Player.objects.get_or_create(directory_number=entry['directory_number'],defaults={'display_name':entry['display_name'],'positions':entry['positions']})
            created+=int(new)
        self.stdout.write(f'{created} player records added. No passwords or accounts created; assign squads after confirmation.')
