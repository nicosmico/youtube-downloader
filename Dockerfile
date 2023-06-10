FROM python:3.10

WORKDIR /app
COPY requirements.txt .

# Install app requirements
RUN pip install -r requirements.txt && python -m pip install --upgrade pytube

CMD [ "flask", "run"]