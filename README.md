# butter_mind

DevButter backend API — chat, guided budget/diagnosis chatbot, and a knowledge base ready for future RAG.

## Local development

```bash
docker compose up -d db
poetry install
poetry run app db migrate
poetry run uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs`.

## Database CLI

```bash
poetry run app db heads
poetry run app db make "description of the change"
poetry run app db migrate
poetry run app db rollback
poetry run app db history
```
