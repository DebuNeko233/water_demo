"""Operator-by-default local role API; no privileged default credentials."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from sample_backend.services.user_access import AccessDenied
from sample_backend.services.water_session import DetectorSettings

router = APIRouter(prefix='/api/users')


class PasswordInput(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class LogoutInput(BaseModel):
    admin_token: str = Field(min_length=1, max_length=128)


class SettingsInput(LogoutInput):
    settings: DetectorSettings


def execute(callback):
    try:
        return callback()
    except AccessDenied as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc


@router.get('/status')
def user_status(request: Request) -> dict:
    return request.app.state.user_access.public_status()


@router.post('/setup')
def admin_setup(body: PasswordInput, request: Request) -> dict:
    return execute(lambda: request.app.state.user_access.configure(body.password))


@router.post('/login')
def admin_login(body: PasswordInput, request: Request) -> dict:
    return execute(lambda: request.app.state.user_access.login(body.password))


@router.post('/logout')
def admin_logout(body: LogoutInput, request: Request) -> dict:
    return execute(lambda: request.app.state.user_access.logout(body.admin_token))


@router.post('/settings')
def admin_save_settings(body: SettingsInput, request: Request) -> dict:
    return execute(lambda: request.app.state.user_access.update_settings(
        body.admin_token, body.settings))
