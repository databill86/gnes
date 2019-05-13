import os
import unittest

from gnes.document import UniSentDocument, MultiSentDocument
from gnes.encoder.w2v import Word2VecEncoder


class TestW2vEncoder(unittest.TestCase):

    def setUp(self):
        dirname = os.path.dirname(__file__)
        self.dump_path = os.path.join(dirname, 'w2v_encoder.bin')

        self.test_docs = []
        self.test_str = []
        with open(os.path.join(dirname, 'tangshi.txt')) as f:
            title = ''
            sents = []
            doc_id = 0
            for line in f:
                line = line.strip()

                if line and not title:
                    title = line
                    sents.append(line)
                elif line and title:
                    sents.append(line)
                elif not line and title and len(sents) > 1:
                    self.test_str.extend(sents)
                    doc = gnes_pb2.Document()
                    doc.id = doc_id
                    doc.text = ' '.join(sents)
                    doc.text_chunks.extend(sents)
                    doc.doc_size = len(sents)

                    doc.is_parsed = True
                    doc.is_encoded = True
                    doc_id += 1
                    sents.clear()
                    title = ''
                    self.test_docs.append(doc)


    def test_encoding(self):
        w2v_encoder = Word2VecEncoder(
            model_dir=os.environ['WORD2VEC_MODEL'],
            pooling_strategy="REDUCE_MEAN")
        vec = w2v_encoder.encode(self.test_str)
        self.assertEqual(vec.shape[0], len(self.test_str))
        self.assertEqual(vec.shape[1], 300)

    def test_dump_load(self):
        w2v_encoder = Word2VecEncoder(
            model_dir=os.environ['WORD2VEC_MODEL'],
            pooling_strategy="REDUCE_MEAN")
        w2v_encoder.dump(self.dump_path)
        w2v_encoder2 = Word2VecEncoder.load(self.dump_path)
        vec = w2v_encoder2.encode(self.test_str)
        self.assertEqual(vec.shape[0], len(self.test_str))
        self.assertEqual(vec.shape[1], 300)

    def tearDown(self):
        if os.path.exists(self.dump_path):
            os.remove(self.dump_path)
