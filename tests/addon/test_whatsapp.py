"""Tests de la lógica de WhatsApp del add-on (sin DB ni red)."""

from urllib.parse import unquote

from addon.whatsapp import (
    build_match_payload,
    mensaje_contacto_rescatista,
    mensaje_familia,
    normalizar_telefono,
    wa_link,
)


class TestNormalizarTelefono:
    def test_none_y_vacio(self):
        assert normalizar_telefono(None) is None
        assert normalizar_telefono("") is None
        assert normalizar_telefono("   ") is None
        assert normalizar_telefono("abc") is None

    def test_local_con_cero_antepone_pais(self):
        # 0412-1234567 (Venezuela) -> 58 4121234567
        assert normalizar_telefono("0412-1234567", "58") == "584121234567"

    def test_internacional_con_mas_se_respeta(self):
        assert normalizar_telefono("+58 412 1234567", "58") == "584121234567"

    def test_doble_cero_se_quita(self):
        assert normalizar_telefono("00584121234567", "58") == "584121234567"

    def test_sin_prefijo_antepone_pais(self):
        assert normalizar_telefono("4121234567", "58") == "584121234567"

    def test_ya_trae_codigo_pais(self):
        assert normalizar_telefono("584121234567", "58") == "584121234567"

    def test_muy_corto_es_invalido(self):
        assert normalizar_telefono("12345", "58") is None

    def test_respeta_otro_pais(self):
        # México (52): número local con 0 no aplica igual, pero el prefijo se antepone.
        assert normalizar_telefono("5512345678", "52") == "525512345678"


class TestWaLink:
    def test_arma_link_con_texto_encodeado(self):
        link = wa_link("0412-1234567", "hola mundo", "58")
        assert link is not None
        assert link.startswith("https://wa.me/584121234567?text=")
        assert "hola mundo" in unquote(link)

    def test_telefono_invalido_devuelve_none(self):
        assert wa_link("abc", "hola", "58") is None


class TestMensajes:
    def test_contacto_rescatista_incluye_nombre_y_refugio(self):
        msg = mensaje_contacto_rescatista(
            nombre_buscada="María", refugio="Refugio Central", negocio="Reencuentros"
        )
        assert "María" in msg
        assert "Refugio Central" in msg
        assert "Reencuentros" in msg

    def test_contacto_rescatista_sin_datos_usa_fallback(self):
        msg = mensaje_contacto_rescatista(nombre_buscada=None, refugio=None)
        assert "la persona que buscas" in msg

    def test_mensaje_familia_incluye_coincidencia_y_refugio(self):
        msg = mensaje_familia(
            nombre_buscada="Juan",
            refugio="Refugio Sur",
            ubicacion="Plaza Bolívar",
            encontrado_por="Ana",
            telefono_responsable="0414-9999999",
            coincidencia=87,
            negocio="Reencuentros",
        )
        assert "87%" in msg
        assert "Refugio Sur" in msg
        assert "Juan" in msg
        assert "Ana" in msg

    def test_build_match_payload_mapea_campos(self):
        m = {
            "familiar_telefono": "0412-1111111",
            "buscada_nombre": "María", "buscada_apellido": "Pérez",
            "refugio": "Refugio Central", "ubicacion": "Plaza Bolívar",
            "encontrado_por": "Ana", "telefono_responsable": "0414-9999999",
            "coincidencia": 87,
        }
        p = build_match_payload(m, "mi_instancia")
        assert p["familiar_telefono"] == "0412-1111111"
        assert p["nombre_buscada"] == "María Pérez"
        assert p["refugio"] == "Refugio Central"
        assert p["coincidencia"] == 87
        assert p["instance_name"] == "mi_instancia"

    def test_build_match_payload_nombre_none_si_falta(self):
        p = build_match_payload({"familiar_telefono": "0412", "coincidencia": 90})
        assert p["nombre_buscada"] is None
        assert p["instance_name"] == ""

    def test_build_match_payload_normaliza_telefono_y_min(self):
        p = build_match_payload(
            {"familiar_telefono": "0412-1111111", "coincidencia": 87},
            "inst", default_country="58", min_coincidencia=80,
        )
        # telefono ya viene normalizado (single-source); n8n no debe re-normalizar.
        assert p["telefono"] == "584121111111"
        assert p["min_coincidencia"] == 80
        assert p["familiar_telefono"] == "0412-1111111"  # raw conservado

    def test_build_match_payload_sin_min_no_incluye_campo(self):
        p = build_match_payload({"familiar_telefono": "0412-1111111", "coincidencia": 90})
        assert "min_coincidencia" not in p


class TestEvolutionConnect:
    def _client(self):
        from addon.config import AddonSettings
        from addon.whatsapp import EvolutionClient
        s = AddonSettings(evolution_url="https://x", evolution_apikey="k",
                          evolution_instance="i")
        return EvolutionClient(s)

    def test_connection_state_anidado(self, monkeypatch):
        c = self._client()
        monkeypatch.setattr(c, "_get", lambda p, t=None: {"instance": {"state": "open"}})
        assert c.connection_state() == "open"

    def test_connection_state_plano(self, monkeypatch):
        c = self._client()
        monkeypatch.setattr(c, "_get", lambda p, t=None: {"state": "connecting"})
        assert c.connection_state() == "connecting"

    def test_connect_qrcode_anidado(self, monkeypatch):
        c = self._client()
        monkeypatch.setattr(c, "_get", lambda p, t=None: {
            "qrcode": {"base64": "data:image/png;base64,AAA", "code": "2@x", "pairingCode": "ABCD"}})
        q = c.connect()
        assert q["base64"] == "data:image/png;base64,AAA"
        assert q["pairingCode"] == "ABCD"

    def test_connect_plano(self, monkeypatch):
        c = self._client()
        monkeypatch.setattr(c, "_get", lambda p, t=None: {"base64": "B", "code": "C", "pairingCode": None})
        q = c.connect()
        assert q["base64"] == "B" and q["code"] == "C"

    def test_connect_respuesta_lista_no_revienta(self, monkeypatch):
        # Evolution a veces devuelve una lista; connect() no debe lanzar AttributeError.
        c = self._client()
        monkeypatch.setattr(c, "_get", lambda p, t=None: [{"x": 1}])
        q = c.connect()
        assert q == {"base64": None, "code": None, "pairingCode": None}

    def test_connection_state_lista_devuelve_unknown(self, monkeypatch):
        c = self._client()
        monkeypatch.setattr(c, "_get", lambda p, t=None: ["weird"])
        assert c.connection_state() == "unknown"


class TestMensajesMore:
    def test_mensaje_familia_omite_ubicacion_igual_a_refugio(self):
        msg = mensaje_familia(
            nombre_buscada="Juan",
            refugio="Refugio Sur",
            ubicacion="Refugio Sur",
            encontrado_por=None,
            telefono_responsable=None,
            coincidencia=70,
        )
        # No debe duplicar la línea de ubicación si es igual al refugio.
        assert msg.count("Refugio Sur") == 1
