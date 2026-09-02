FROM python:3.12-slim

WORKDIR /app

COPY docker-requirements.txt .

RUN pip install --no-cache-dir -r docker-requirements.txt


COPY FLUX_ph_dashboard.py .
COPY preprocessing.py .
# Watch out to mount the data directory using -v on docer run
# or use the docker compose
RUN mkdir -p /app/data && mkdir -p /app/resources

EXPOSE 8501

CMD ["sh", "-c", "python preprocessing.py && streamlit run FLUX_ph_dashboard.py --server.address=0.0.0.0"]
