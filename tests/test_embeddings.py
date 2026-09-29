import numpy as np
import pytest

from rag.embeddings import media_normalizada


def test_media_ignora_padding_e_normaliza():
    estados = np.array([[[3.0, 0.0], [0.0, 4.0], [100.0, 100.0]]])  # o terceiro token é padding
    mascara = np.array([[1, 1, 0]])
    v = media_normalizada(estados, mascara)
    assert v.shape == (1, 2)
    assert v[0] == pytest.approx([0.6, 0.8])  # média (1.5, 2.0) com norma 1
    assert np.linalg.norm(v[0]) == pytest.approx(1.0)
