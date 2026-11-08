FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/user
RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user:user service ./service
COPY --chown=user:user config ./config
COPY --chown=user:user README.md .
USER user
EXPOSE 7860
CMD ["uvicorn", "service.api:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
