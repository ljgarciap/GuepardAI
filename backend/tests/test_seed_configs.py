"""
test_seed_configs.py — Guard de integridad de utils/seed.py.

Cubre una clase de bug real encontrada al implementar
docs/specs/coherencia-artistica-pipeline.md: una `description` de más de 255
caracteres en una entrada de CONFIGS revienta el commit final de seed_data()
con StringDataRightTruncation — y como ese commit es atómico, arrastra consigo
inserts no relacionados (en ese caso, el FooterConfig por defecto), fallando
en silencio (main.py solo imprime un warning, no vuelve a lanzar la excepción).
"""
import pytest

import models
from utils.seed import CONFIGS

DESCRIPTION_MAX_LEN = models.SystemConfig.description.property.columns[0].type.length


@pytest.mark.unit
class TestSeedConfigsIntegrity:

    def test_no_description_exceeds_the_column_length(self):
        offenders = [
            (cfg["key"], len(cfg.get("description") or ""))
            for cfg in CONFIGS
            if len(cfg.get("description") or "") > DESCRIPTION_MAX_LEN
        ]
        assert offenders == [], (
            f"description excede SystemConfig.description (String({DESCRIPTION_MAX_LEN})): {offenders}"
        )

    def test_no_duplicate_keys_in_configs(self):
        keys = [cfg["key"] for cfg in CONFIGS]
        duplicates = {k for k in keys if keys.count(k) > 1}
        assert duplicates == set(), f"keys duplicadas en CONFIGS: {duplicates}"

    def test_every_config_has_key_and_value(self):
        for cfg in CONFIGS:
            assert cfg.get("key"), f"entrada sin key: {cfg}"
            assert cfg.get("value") is not None, f"entrada sin value: {cfg['key']}"
