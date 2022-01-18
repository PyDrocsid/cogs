from aiohttp import ClientSession


class PistonException(BaseException):
    @property
    def error(self) -> str:
        return self.args[0]["message"]


class PistonAPI:
    ENVIRONMENTS_URL = "https://emkc.org/api/v2/piston/runtimes"
    EXECUTE_URL = "https://emkc.org/api/v2/piston/execute"

    def __init__(self):
        self.environments: dict[str, str] = {}
        self.aliases: dict[str, str] = {}

    def get_language(self, language: str) -> str | None:
        if language in self.environments:
            return language

        return self.aliases.get(language)

    async def load_environments(self):
        async with ClientSession() as session, session.get(self.ENVIRONMENTS_URL) as response:
            if response.status != 200:
                raise PistonException

            environments = await response.json()

        self.environments = {env["language"]: env["version"] for env in environments}
        self.aliases = {alias: env["language"] for env in environments for alias in env["aliases"]}

    async def run_code(self, language: str, source: str) -> dict:
        async with ClientSession() as session, session.post(
            PistonAPI.EXECUTE_URL,
            json={"language": language, "version": self.environments[language], "files": [{"content": source}]},
        ) as response:
            if response.status != 200:
                raise PistonException(await response.json())

            return await response.json()
