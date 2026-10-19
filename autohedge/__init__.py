from autohedge.env_loader import load_env

load_env()

__all__ = ["AutoHedge"]


def __getattr__(name):
    # Lazy so that importing submodules does not load swarms.
    if name == "AutoHedge":
        from autohedge.main import AutoHedge

        return AutoHedge
    raise AttributeError(name)
