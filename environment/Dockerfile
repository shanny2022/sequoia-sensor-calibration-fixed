FROM python:3.11-slim@sha256:a3ab0b966bc4e91546a033e22093cb840908979487a9fc0e6e38295747e49ac0

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# Scientific computing and test runner
RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    pandas==2.2.2 \
    scipy==1.11.3 \
    pytest==7.4.2 \
    pytest-json-ctrf==0.5.0

# Copy input data into the image so it is available to the agent and oracle
COPY data/ /app/data/

# Create required log directories for the verifier reward file
RUN mkdir -p /logs/verifier /logs/agent && \
    chmod -R 755 /logs

# Create outputs directory
RUN mkdir -p /app/outputs
