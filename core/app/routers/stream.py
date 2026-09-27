import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.adapters.alpaca_data import MarketDataHub
from app.dependencies import get_market_data_hub

router = APIRouter(tags=["stream"])


@router.websocket("/ws/live")
async def live_stream(
    websocket: WebSocket,
    hub: MarketDataHub = Depends(get_market_data_hub),
) -> None:
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue()

    async def sender() -> None:
        while True:
            message = await queue.get()
            await websocket.send_json(message)

    sender_task = asyncio.create_task(sender())
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            symbols = data.get("symbols", [])
            if action == "subscribe":
                await hub.subscribe(queue, symbols)
            elif action == "unsubscribe":
                await hub.unsubscribe(queue, symbols or None)
    except WebSocketDisconnect:
        pass
    finally:
        sender_task.cancel()
        await hub.unsubscribe(queue, None)
