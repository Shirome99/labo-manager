"""Version et environnement de l'application (tâche 31) : route publique, affichée en bas du menu."""
from app.core.config import VERSION


async def test_version_publique(clients):
    r = await clients[None].get("/api/version")
    assert r.status_code == 200
    assert r.json() == {"version": VERSION, "environnement": "test"}
