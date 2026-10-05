"""Topic exchange, mensagens persistentes, publisher confirms e ack manual."""
import asyncio
import json
import logging
import os
import aio_pika
from .relogio_vetorial import validar_vetor

log = logging.getLogger(__name__)
EXCHANGE = "iceibank.eventos"


class PublicacaoRecusada(Exception):
    """O broker recusou a mensagem ou não existe uma rota para ela."""


class BrokerIndisponivel(Exception):
    """Nenhuma tentativa de envio foi iniciada."""


class Mensageria:
    def __init__(self, id_agencia: int, ao_receber):
        self.id_agencia = id_agencia
        self.ao_receber = ao_receber
        self.conexao = self.canal = self.exchange = None

    @property
    def disponivel(self):
        return bool(self.conexao and self.conexao.connected.is_set()
                    and self.canal and not self.canal.is_closed)

    async def iniciar(self):
        url = os.environ.get("RABBITMQ_URL")
        if not url:
            raise RuntimeError("Defina RABBITMQ_URL antes de iniciar a agencia.")
        try:
            self.conexao = await aio_pika.connect_robust(url, timeout=8)
            self.canal = await self.conexao.channel(publisher_confirms=True, on_return_raises=True)
            await self.canal.set_qos(prefetch_count=1)
            self.exchange = await self.canal.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
            filas = []
            for id_agencia in range(3):
                fila = await self.canal.declare_queue(f"fila-agencia-{id_agencia}", durable=True)
                await fila.bind(self.exchange, f"agencia.{id_agencia}.creditar")
                filas.append(fila)
            await filas[self.id_agencia].consume(self._consumir, no_ack=False)
        except Exception:
            await self.fechar()
            raise RuntimeError("Nao foi possivel iniciar RabbitMQ; confira RABBITMQ_URL e o broker.") from None

    async def fechar(self):
        if self.conexao:
            await self.conexao.close()

    async def publicar(self, routing_key: str, evento: dict):
        if not self.disponivel:
            raise BrokerIndisponivel()
        mensagem = aio_pika.Message(
            json.dumps(evento, allow_nan=False).encode(), content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=evento["transferenciaId"], correlation_id=evento["transferenciaId"],
        )
        try:
            await self.exchange.publish(mensagem, routing_key, mandatory=True, timeout=8)
        except aio_pika.exceptions.DeliveryError:
            raise PublicacaoRecusada() from None

    async def _consumir(self, mensagem: aio_pika.IncomingMessage):
        try:
            corpo = json.loads(mensagem.body)
            if not isinstance(corpo, dict):
                raise ValueError("Mensagem deve ser objeto.")
            validar_vetor(corpo.get("vetorEnvio", []), 3)
            await self.ao_receber(corpo)
        except (ValueError, TypeError, KeyError):
            log.warning("MENSAGEM_REJEITADA agencia=%s id=%s", self.id_agencia, mensagem.message_id)
            await mensagem.reject(requeue=False)
        except asyncio.CancelledError:
            raise
        except Exception as erro:
            log.warning("CONSUMO_REPETIR agencia=%s erro=%s", self.id_agencia, type(erro).__name__)
            await asyncio.sleep(1)
            if not mensagem.channel.is_closed:
                await mensagem.nack(requeue=True)
        else:
            await mensagem.ack()
