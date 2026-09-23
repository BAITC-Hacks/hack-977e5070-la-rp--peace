"""FastAPI dependencies shared by the routers."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from la_rp_peace.config import Settings


def get_session(request: Request) -> Iterator[Session]:
    """Yield a database session bound to the app's engine for one request."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def get_app_settings(request: Request) -> Settings:
    """Return the settings the app was created with."""
    settings: Settings = request.app.state.settings
    return settings


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
