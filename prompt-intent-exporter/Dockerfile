FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY exporter.py .

# Model artifacts (model.int8.onnx, tokenizer.json, meta.json) are mounted at /model
# — produced by prompt-intent-classifier/src/export_onnx.py. Kept out of the image so
# the model can be updated without a rebuild and prompt-derived weights stay out of git.

RUN useradd --system --no-create-home appuser
USER appuser

EXPOSE 9107
ENTRYPOINT ["python", "-u", "exporter.py"]
