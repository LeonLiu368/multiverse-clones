# Seed-init image: fetches this task's APEX fixtures from the public mercor/APEX-SWE
# dataset at runtime and converts them into the clone seed files, written to named
# volumes the ticketvector/slack/gauge sidecars mount. Keeps repo git light.
FROM mirror.gcr.io/library/python:3.12-slim
RUN pip install --no-cache-dir "huggingface_hub>=0.25"
COPY apex_to_clones.py /seed/apex_to_clones.py
COPY run.sh /seed/run.sh
RUN chmod +x /seed/run.sh
ENTRYPOINT ["bash", "/seed/run.sh"]
