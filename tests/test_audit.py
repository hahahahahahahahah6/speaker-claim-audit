"""Spec 1–43; generated phrase tests each cover the literal in their name/docstring."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from speaker_claim_audit.audit import audit, claims, evidence, normalize
from speaker_claim_audit.phrases import SPEAKER, NOSPEAKER
from tests.cases import GOOD, BAD

ROOT = Path(__file__).resolve().parents[1]


class AuditTests(unittest.TestCase):
    def fixture(self, doc='plays audio', source=None, filename='app.py'):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / 'README.md').write_text(doc)
        if source is not None:
            target = root / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source)
        return root

    def cli(self, root, *args):
        return subprocess.run([sys.executable, '-m', 'speaker_claim_audit', str(root), *args], capture_output=True, text=True)

    def assert_bad(self, source):
        root = self.fixture(source=source)
        result = audit(root)
        self.assertEqual(result['findings'][0]['rule'], 'documented-speaker-claim-false')
        self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(self.cli(root).returncode, 2)

    def test_29_no_speaker(self):
        root = self.fixture('no audio playback', GOOD[0])
        self.assertEqual(audit(root)['findings'], [{'rule':'documented-no-speaker-claim-false','severity':'HIGH','message':'Local-emission denial conflicts with production evidence.'}])
        self.assertEqual(self.cli(root).returncode, 2)

    def test_30_no_claim(self):
        self.assertEqual(audit(self.fixture('A utility.', GOOD[0]))['verdict'], 'PASS')

    def test_31_bare_noun(self):
        self.assertEqual(audit(self.fixture('the speaker chapter explains setup', BAD[0]))['claims'], {'positive':False,'negative':False})

    def test_32_user_instruction(self):
        self.assertEqual(audit(self.fixture('connect your speakers before starting', BAD[0]))['verdict'], 'PASS')

    def test_33_speech(self):
        self.assertEqual(audit(self.fixture('speaks answers aloud', BAD[7]))['verdict'], 'PASS')

    def test_34_export(self):
        self.assertEqual(audit(self.fixture('exports audio for later listening', 'seg.export("x.wav")'))['verdict'], 'PASS')

    def test_35_no_source(self):
        self.assertEqual(audit(self.fixture())['findings'][0]['severity'], 'HIGH')
        self.assertEqual(audit(self.fixture('no audio playback'))['verdict'], 'PASS')

    def test_36_tests_only(self):
        for filename in ['tests/audio.py', 'test_audio.py', 'audio_test.py']:
            with self.subTest(filename=filename):
                root = self.fixture(source=GOOD[0], filename=filename)
                self.assertEqual(audit(root)['findings'][0]['severity'], 'MEDIUM')
                self.assertEqual(self.cli(root).returncode, 0)
                self.assertEqual(self.cli(root, '--fail-on', 'MEDIUM').returncode, 2)

    def test_37_fences_inline(self):
        for fence in ['```', '~~~~']:
            self.assertEqual(claims(fence+'\nplays audio\n'+fence), (False,False))
        self.assertEqual(audit(self.fixture('`plays audio`'))['findings'][0]['severity'], 'HIGH')

    def test_38_negation(self):
        self.assertEqual(claims('does not play audio through your speakers'), (False,True))
        self.assertEqual(claims("doesn't play audio through your speakers"), (False,True))

    def test_39_self_audit(self):
        result = audit(ROOT)
        self.assertEqual(result['verdict'], 'PASS')
        self.assertEqual(result['claims'], {'positive':False,'negative':False})
        text = normalize((ROOT/'README.md').read_text())
        for phrase in SPEAKER + NOSPEAKER:
            self.assertIsNone(re.search(r'\b'+re.escape(phrase)+r'\b', text), phrase)

    def test_40_cli(self):
        root = self.fixture(source=GOOD[0])
        self.assertEqual(self.cli(root, '--version').stdout.strip(), '0.1.0')
        self.assertEqual(json.loads(self.cli(root, '--json').stdout)['verdict'], 'PASS')
        self.assertIn('app.py:2 playsound', self.cli(root, '--verbose').stdout)
        self.assertEqual(self.cli(root, '--ignore', 'README.md', '--ignore', '*.py').returncode, 0)
        self.assertEqual(self.cli(root/'missing').returncode, 1)
        self.assertEqual(self.cli(root, '--fail-on', 'LOW').returncode, 1)
        root.chmod(0)
        self.addCleanup(root.chmod, 0o700)
        self.assertEqual(self.cli(root).returncode, 1)

    def test_41_env_guard(self):
        original = Path.read_text
        def guarded(path, *args, **kwargs):
            self.assertNotEqual(path.name, '.env')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', guarded):
            audit(ROOT)

    def test_42_packaging(self):
        for path in list((ROOT/'speaker_claim_audit').glob('*.py')) + list((ROOT/'tests').glob('*.py')) + [ROOT/'README.md', ROOT/'pyproject.toml']:
            self.assertIsNone(re.search(r'(?<![\w-])py' + r'thon(?![\w-])', path.read_text()), str(path))
        config = (ROOT/'pyproject.toml').read_text()
        self.assertIn('setuptools>=77', config)
        self.assertIn('license = "MIT"', config)
        self.assertIn('recursive-include tests', (ROOT/'MANIFEST.in').read_text())

    def test_aliases_and_constructors(self):
        routes = [
            'from pygame import mixer as mx\nmx.music.play()',
            'from pygame import mixer as mx\nx=mx.Sound("x")\nx.play()',
            'from simpleaudio import WaveObject as W\nself.w=W.from_wave_file("x")\nself.w.play()',
            'from winsound import MessageBeep as b\nb()',
            'from sounddevice.extra import play as go\ngo(data)',
            'from playsound2.extra import playsound as go\ngo("x")',
            'from pydub.playback import play as go\ngo(seg)',
            'from pyaudio import PyAudio as P\nself.p=P()\nself.s=self.p.open(output=True)\nself.s.write(data)',
            'import pyaudio as pa\npa.PyAudio().open(output=True).write(data)',
        ]
        for source in routes:
            with self.subTest(source=source):
                self.assertTrue(evidence(source))

    def test_additional_exclusions(self):
        for source in [
            'from simpleaudio import WaveObject\nw=WaveObject(data)',
            'from pydub import play\nplay(seg)',
            'from pydub import AudioSegment\ns=AudioSegment()\ns.export("x")',
            'import soundfile\nsoundfile.write("x",data)',
            'from scipy.io import wavfile\nwavfile.write("x",1,data)',
            'from gtts import gTTS\ngTTS("hello").save("x")',
            'import mutagen\nmutagen.File("x")',
            'import tinytag\ntinytag.TinyTag.get("x")',
            'def play_sound():\n print("speaker")\nplay_sound()',
            '@app.get("/")\ndef f():\n return "speaker"',
            'import pyaudio\np=pyaudio.PyAudio()\np.open(output=True)',
            'import pyaudio\np=pyaudio.PyAudio()\ns=p.open(output=1)\ns.write(data)',
            '"import winsound; winsound.Beep(1,2)"',
            '# import winsound; winsound.Beep(1,2)',
            'import pygame_fake as pg\npg.mixer.music.play()',
        ]:
            with self.subTest(source=source):
                self.assertFalse(evidence(source))
        for library in ['playsound','playsound2','pygame','sounddevice','simpleaudio','winsound','pyaudio','pydub.playback']:
            self.assertFalse(evidence('import '+library))
        for player in ['ffplay','aplay','paplay','afplay']:
            self.assertFalse(evidence('import subprocess\nsubprocess.run(["'+player+'","x"])'))

    def test_scope_binding_and_symlinks(self):
        root = self.fixture(source='s.play()')
        (root/'other.py').write_text('import pygame\ns=pygame.mixer.Sound("x")')
        self.assertEqual(audit(root)['verdict'], 'FAIL')
        for folder in ['docs','examples','fixtures']:
            target=root/folder/'emit.py';target.parent.mkdir(exist_ok=True);target.write_text(GOOD[0])
        (root/'link.py').symlink_to(root/'examples/emit.py')
        self.assertEqual(audit(root)['verdict'], 'FAIL')

    def test_docs_scope_and_asymmetry(self):
        root = self.fixture('neutral', GOOD[0])
        doc=root/'tests/docs/nested/guide.md';doc.parent.mkdir(parents=True);doc.write_text('no audio playback')
        self.assertEqual(audit(root)['findings'][0]['severity'], 'HIGH')
        self.assertEqual(audit(root, ['tests/docs/*'])['verdict'], 'PASS')

    def test_normalization_boundaries_paragraphs(self):
        self.assertEqual(claims('PLAYS-AUDIO\n through your speakers'), (True,False))
        self.assertEqual(claims('plays\n\naudio'), (False,False))
        self.assertEqual(claims('displays audio'), (False,False))
        self.assertEqual(claims('plays audio. no audio playback.'), (True,True))
        root=self.fixture('plays audio. no audio playback.')
        self.assertEqual(len(audit(root)['findings']),1)

    def test_syntax_error(self):
        self.assertFalse(evidence('def broken('))


def add_good(index, source):
    def test(self):
        root = self.fixture(source=source)
        self.assertEqual(audit(root)['verdict'], 'PASS')
        self.assertTrue(audit(root)['evidence'])
        self.assertEqual(self.cli(root).returncode, 0)
    setattr(AuditTests, 'test_%02d_good_route' % index, test)


for index, source in enumerate(GOOD, 1):
    add_good(index, source)
for index, source in enumerate(BAD, 18):
    def test(self, source=source):
        self.assert_bad(source)
    setattr(AuditTests, 'test_%02d_bad_route' % index, test)

# Exhaustion: one individually discoverable test for every exact template.
for family, phrases in [('positive',SPEAKER), ('negative',NOSPEAKER)]:
    for index, phrase in enumerate(phrases):
        def test(self, phrase=phrase, family=family):
            expected = (True,False) if family == 'positive' else (False,True)
            self.assertEqual(claims(phrase), expected)
            root = self.fixture(phrase, None if family == 'positive' else GOOD[0])
            self.assertEqual(len(audit(root)['findings']), 1)
            self.assertEqual(audit(root)['findings'][0]['severity'], 'HIGH')
        test.__doc__ = phrase
        setattr(AuditTests, 'test_43_%s_%02d_%s' % (family,index,phrase.replace(' ','_')), test)
