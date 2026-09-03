import re
import uuid

from app.core.paths import FRONTEND_INDEX, FRONTEND_STATIC_DIR
from app.models import Aluno, TipoAluno


def test_build_frontend_esta_disponivel():
    assert FRONTEND_INDEX.is_file()
    assert FRONTEND_STATIC_DIR.joinpath("logo.png").is_file()


def test_paginas_do_painel_servem_o_react(client):
    for caminho in ("/login", "/painel"):
        response = client.get(caminho)
        assert response.status_code == 200
        assert '<div id="root"></div>' in response.text


def test_assets_referenciados_no_index_sao_servidos(client):
    html = FRONTEND_INDEX.read_text(encoding="utf-8")
    assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', html)

    assert assets
    for asset in assets:
        response = client.get(asset)
        assert response.status_code == 200

    logo = client.get("/static/logo.png")
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"


def test_portal_valido_serve_o_react(client, db_session):
    token = str(uuid.uuid4())
    db_session.add(Aluno(
        nome="Aluno",
        sobrenome="Portal",
        telefone="5511999999999",
        token_acesso=token,
        tipo=TipoAluno.VIP,
    ))
    db_session.commit()

    response = client.get(f"/portal/{token}")

    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text
