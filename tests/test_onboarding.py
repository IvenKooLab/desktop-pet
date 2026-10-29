"""Exercise first-run scheduling without a Tk window or the user's configuration."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WelcomeTests(unittest.TestCase):
    def make_pet(self):
        tree = ast.parse((ROOT/'pet.py').read_text())
        cls = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name == 'Pet')
        method = next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name == '_maybe_welcome')
        saved, calls, queue = [], [], []
        scope = {'pet_config': SimpleNamespace(save=lambda cfg: saved.append(dict(cfg)))}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'pet.py','exec'),scope)
        pet = type('Pet',(),{'_maybe_welcome':scope['_maybe_welcome']})()
        pet.config={}; pet.state='IDLE'; pet._embedded_display=False
        pet._host_action=False; pet._bridge_on=True; pet.host=SimpleNamespace(mode=None)
        pet.root=SimpleNamespace(after=lambda _delay, callback: queue.append(callback))
        pet._menu_text=lambda cn,en:en
        pet.say=lambda *args,**kwargs:calls.append((args,kwargs))
        return pet,saved,calls,queue

    def test_pinned_idle_starts_without_landing_and_records_only_after_display(self):
        pet,saved,calls,queue=self.make_pet()
        pet._maybe_welcome();pet._maybe_welcome()
        self.assertEqual(len(queue),1)
        self.assertEqual(saved,[])
        queue.pop(0)()
        self.assertEqual(len(calls),1)
        self.assertTrue(saved[0]['welcomed'])
        pet._maybe_welcome()
        self.assertEqual(queue,[])

    def test_hidden_or_busy_welcome_is_deferred_and_not_marked_read(self):
        pet,saved,calls,queue=self.make_pet()
        pet._embedded_display=True
        pet._maybe_welcome();queue.pop(0)()
        self.assertEqual(calls,[]);self.assertEqual(saved,[])
        pet._embedded_display=False;pet.host.mode='working'
        queue.pop(0)()
        self.assertEqual(calls,[]);self.assertEqual(saved,[])
        pet.host.mode=None;pet.state='SLEEP'
        queue.pop(0)()
        self.assertEqual(calls,[]);self.assertEqual(saved,[])
        pet.state='IDLE';queue.pop(0)()
        self.assertEqual(len(calls),1)
        self.assertTrue(pet.config['welcomed'])


if __name__ == '__main__': unittest.main()
