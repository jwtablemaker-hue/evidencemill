import unittest

from evidencemill.document import OcrWord
from evidencemill.illustration import associate_callouts, recognize_callouts


class IllustrationTests(unittest.TestCase):
    def test_callout_geometry(self):
        words = (
            OcrWord("1", (0, 0, 10, 10)),
            OcrWord("Motor", (20, 0, 60, 10)),
            OcrWord("2", (0, 50, 10, 60)),
            OcrWord("Battery", (20, 50, 70, 60)),
        )
        self.assertEqual([x.callout for x in recognize_callouts(words)], ["1", "2"])
        links = associate_callouts(words)
        self.assertEqual(links[0].target_label, "Motor")
        self.assertEqual(links[1].target_label, "Battery")


if __name__ == "__main__":
    unittest.main()
