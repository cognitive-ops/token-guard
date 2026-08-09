FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY quality_rubric.py exporter.py .

# Disk cache lives on a mounted volume (see docker-compose.yml) so a container
# restart never re-scores (re-spends on) prompts it already paid to score.
RUN mkdir -p /cache && useradd --system --no-create-home appuser && chown appuser /cache
USER appuser

EXPOSE 9110
ENTRYPOINT ["python", "-u", "exporter.py"]
