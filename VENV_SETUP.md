# Opsætning af virtuelt Python-miljø

Projektet er beregnet til **Python 3.12**. Det virtuelle miljø skal ligge i mappen `.venv` i projektets rod.

`.venv` er tilføjet til `.gitignore` og bliver derfor ikke sendt til Bitbucket. Hver udvikler opretter sit eget miljø og installerer pakkerne fra `requirements.txt`.

## Windows CMD

Åbn CMD i projektmappen, og kør:

```cmd
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Når miljøet er aktivt, står der normalt `(.venv)` foran kommandoprompten.

## Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Hvis PowerShell blokerer aktiveringsscriptet, kan du midlertidigt tillade det i den aktuelle terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Linux og macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

På nogle Linux-distributioner skal understøttelse af virtuelle miljøer installeres først, eksempelvis pakken `python3.12-venv`.

## Verificering

Kontrollér Python-versionen og de installerede dependencies:

```bash
python --version
python -m pip check
python -m pytest -q
```

Python-versionen bør være `3.12.x`, `pip check` bør skrive `No broken requirements found`, og testpakken bør bestå.

## VS Code

1. Åbn Command Palette med `Ctrl+Shift+P`.
2. Vælg **Python: Select Interpreter**.
3. Vælg Python-interpreteren fra projektets `.venv`.

Den ligger normalt her:

- Windows: `.venv\Scripts\python.exe`
- Linux/macOS: `.venv/bin/python`

## Deaktivering

Miljøet kan forlades med:

```bash
deactivate
```

## Miljøvariabler

Det virtuelle miljø indeholder Python-pakker, men ikke projektets konfiguration. Kopiér eksempelkonfigurationen separat:

Windows CMD:

```cmd
copy .env.example .env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

Ret derefter mindst `API_KEY` og `DATABASE_URL` i `.env`. Filen `.env` er ignoreret af Git og må ikke indeholde secrets, som committes til Bitbucket.

