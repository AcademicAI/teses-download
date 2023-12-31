import requests
import pathlib
from bs4 import BeautifulSoup
import tenacity
import shutil
from tqdm.auto import tqdm
from rich.console import Console
from tenacity import stop_after_attempt, wait_fixed, wait_random
from .cache import Cache


@tenacity.retry(
    stop=stop_after_attempt(2),
    wait=wait_fixed(4) + wait_random(0, 3),
    reraise=True,
    retry=tenacity.retry_if_exception_type(requests.exceptions.HTTPError)
    | tenacity.retry_if_exception_type(requests.exceptions.ConnectionError)
    | tenacity.retry_if_exception_type(requests.exceptions.Timeout)
    | tenacity.retry_if_exception_type(requests.exceptions.RequestException),
)
def download_pdf(
    url: str, id: int, output_dir: str, download_timeout: int = 60
) -> str | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:88.0) Gecko/20100101 Firefox/88.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Connection": "keep-alive",
        "Accept-Language": "pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Host": "sucupira.capes.gov.br",
    }

    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with requests.session() as session:
        r = session.get(url, headers=headers, timeout=7)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        form = soup.find("form", id="download")

        if not form:
            return None

        form_data = {
            i.get("name"): i.get("value") for i in form.find_all("input")
        }
        form_data[
            "download:link_download_arquivo"
        ] = "download:link_download_arquivo"

        filename = soup.find("a", id="download:link_download_arquivo")
        filename = filename.get_text() if filename else ""

        if not filename:
            return None

        filepath = output_dir / f"{id}-{filename}"
        filepath = filepath.with_name(
            f"{filepath.stem[:200]}{filepath.suffix}"
        )

        with session.post(
            url,
            data=form_data,
            stream=True,
            headers={
                **headers,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/",
                "Referer": url,
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://sucupira.capes.gov.br",
            },
            timeout=download_timeout,
        ) as resp:
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                shutil.copyfileobj(resp.raw, f)
        return str(filepath)


def download_multiple_pdfs(
    urls: list[str], output_dir: str, cache: Cache, timeout: int = 60
) -> list:
    console = Console()
    for url in tqdm(urls, desc=f"Baixando arquivos com timeout de {timeout}s"):
        current_id = url.split("=")[-1]
        if not current_id.isdigit():
            console.log(
                f":x: Não foi possível obter o id do arquivo: {url}",
                style="bold red1",
            )
            continue
        if current_id in cache:
            continue
        try:
            filepath = download_pdf(url, current_id, output_dir, timeout)
            cache[current_id] = filepath
        except requests.exceptions.ConnectionError:
            console.log(f":x: Connection error: {url}", style="bold red1")
        except requests.exceptions.Timeout:
            console.log(f":x: Timeout error: {url}", style="bold red1")
        except requests.exceptions.HTTPError as e:
            console.log(f":x: HTTP error: {url} - {e}", style="bold red1")
        except requests.exceptions.RequestException as e:
            console.log(f":x: Request error: {url} - {e}", style="bold red1")
        except KeyboardInterrupt:
            console.log(f":warning: Keyboard interrupt", style="bold red1")
            return
        except Exception as e:
            console.log(
                f":skull: Unknown error: {url} - {e}", style="bold red1"
            )
