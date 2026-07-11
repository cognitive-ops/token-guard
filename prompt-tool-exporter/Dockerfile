FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY exporter.py .

# Drop root: run as an unprivileged user (DS-0002).
RUN useradd --system --no-create-home appuser
USER appuser

EXPOSE 9108
ENTRYPOINT ["python", "-u", "exporter.py"]
