from fastapi import Request
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.jeton import utilisateur_requete

# pool_pre_ping : Neon (démo) met la base en veille et coupe les connexions inactives
engine = create_async_engine(settings.url_sqlalchemy, echo=False, pool_pre_ping=True,
                             connect_args=settings.connect_args)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def transmettre_utilisateur(session: AsyncSession, nom: str | None) -> None:
    """
    Journal d'audit (audit_donnees) : à chaque début de transaction, l'utilisateur
    applicatif est transmis à PostgreSQL (équivalent de SET LOCAL lims.utilisateur),
    pour que les triggers d'audit l'enregistrent. Valable pour toutes les transactions
    de la session (une requête peut en ouvrir plusieurs : commit puis refresh...).
    """
    if not nom:
        return

    @event.listens_for(session.sync_session, "after_begin")
    def _utilisateur(_sess, _transaction, connection):
        connection.execute(text("SELECT set_config('lims.utilisateur', :u, true)"), {"u": nom})


async def get_db(request: Request) -> AsyncSession:
    async with SessionLocal() as session:
        transmettre_utilisateur(session, (utilisateur_requete(request) or {}).get("username"))
        yield session
