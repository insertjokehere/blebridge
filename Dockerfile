FROM python:3.6

ENV PYTHONUNBUFFERED=1

WORKDIR /src

ADD requirements.txt /src

RUN pip install -r requirements.txt

ADD . /src

CMD ["python", "-m", "blebridge"]
