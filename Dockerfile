FROM python:3.10

WORKDIR /app
COPY . /app

RUN pip install -r requirements.txt && python -m pip install --upgrade pytube

EXPOSE 80

ENV FLASK_APP=app/app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=80

CMD ["flask", "run", "--port", "80", "--host", "0.0.0.0"]