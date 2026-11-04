FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# hrc-015 (DEC-SCOPE-379 D1, Q-15): headless LibreOffice Writer converts DOC/DOCX resumes and documents to PDF previews (worker).
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl libreoffice-writer-nogui fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
