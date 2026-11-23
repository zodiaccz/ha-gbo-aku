from __future__ import annotations
import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

class GboError(Exception):
    pass

class GboConnectionError(GboError):
    pass

class GboProtocolError(GboError):
    pass

def modbus_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return crc & 0xFFFF

def _append_crc(frame: bytes) -> bytes:
    crc = modbus_crc16(frame)
    return frame + bytes((crc & 0xFF, (crc >> 8) & 0xFF))

def _check_crc(frame: bytes) -> None:
    if len(frame) < 4:
        raise GboProtocolError("Response is too short")
    expected = modbus_crc16(frame[:-2])
    received = frame[-2] | (frame[-1] << 8)
    if received != expected:
        raise GboProtocolError(
            f"CRC mismatch: received 0x{received:04X}, expected 0x{expected:04X}"
        )

class GboClient:
    def __init__(self, host: str, port: int, slave_id: int, timeout: float = 2.0) -> None:
        self.host = str(host)
        self.port = int(port)
        self.slave_id = int(slave_id)
        self.timeout = float(timeout)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self.paused = False

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        if self.paused:
            raise GboConnectionError("GBO-Aku communication is disabled")
        if self.connected:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        except (TimeoutError, OSError) as err:
            await self.close()
            raise GboConnectionError(
                f"Cannot connect to {self.host}:{self.port}: {err}"
            ) from err
        if self.paused:
            await self.close()
            raise GboConnectionError("GBO-Aku communication is disabled")

    async def close(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def set_paused(self, paused: bool) -> None:
        self.paused = paused
        if paused:
            await self.close()

    async def _read_exactly(self, count: int) -> bytes:
        if self._reader is None:
            raise GboConnectionError("TCP connection is not open")
        try:
            async with asyncio.timeout(self.timeout):
                return await self._reader.readexactly(count)
        except (TimeoutError, asyncio.IncompleteReadError, OSError) as err:
            await self.close()
            raise GboConnectionError(f"Receive failed: {err}") from err

    async def _receive_response(self) -> bytes:
        head = await self._read_exactly(2)
        function = head[1]
        if function & 0x80:
            return head + await self._read_exactly(3)
        if function in (0x03, 0x04):
            bc = await self._read_exactly(1)
            return head + bc + await self._read_exactly(bc[0] + 2)
        if function == 0x10:
            return head + await self._read_exactly(6)
        raise GboProtocolError(f"Unsupported function 0x{function:02X}")

    @asynccontextmanager
    async def exclusive(self) -> AsyncIterator[None]:
        """Hold the Modbus transport lock across a multi-request sequence."""
        async with self._lock:
            yield

    async def _transaction_unlocked(self, pdu: bytes) -> bytes:
        """Run one transaction while the caller already owns the lock."""
        if self.paused:
            raise GboConnectionError("GBO-Aku communication is disabled")
        await self.connect()
        if self._writer is None:
            raise GboConnectionError("TCP connection is not open")
        try:
            self._writer.write(_append_crc(pdu))
            await self._writer.drain()
            response = await self._receive_response()
        except GboError:
            await self.close()
            raise
        except (OSError, ConnectionError) as err:
            await self.close()
            raise GboConnectionError(f"Transaction failed: {err}") from err

        _check_crc(response)
        if response[0] != self.slave_id:
            raise GboProtocolError(
                f"Unexpected slave {response[0]}, expected {self.slave_id}"
            )
        req_fn = pdu[1]
        if response[1] == (req_fn | 0x80):
            raise GboProtocolError(
                f"Modbus exception 0x{response[2]:02X} for function 0x{req_fn:02X}"
            )
        if response[1] != req_fn:
            raise GboProtocolError(
                f"Unexpected function 0x{response[1]:02X}, expected 0x{req_fn:02X}"
            )
        return response

    async def _transaction(self, pdu: bytes) -> bytes:
        async with self._lock:
            return await self._transaction_unlocked(pdu)

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        async with self._lock:
            return await self.read_input_registers_unlocked(address, count)

    async def read_input_registers_unlocked(self, address: int, count: int) -> list[int]:
        pdu = bytes((
            self.slave_id, 0x04,
            (address >> 8) & 0xFF, address & 0xFF,
            (count >> 8) & 0xFF, count & 0xFF,
        ))
        return self._decode_read(await self._transaction_unlocked(pdu), count)

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        async with self._lock:
            return await self.read_holding_registers_unlocked(address, count)

    async def read_holding_registers_unlocked(self, address: int, count: int) -> list[int]:
        pdu = bytes((
            self.slave_id, 0x03,
            (address >> 8) & 0xFF, address & 0xFF,
            (count >> 8) & 0xFF, count & 0xFF,
        ))
        return self._decode_read(await self._transaction_unlocked(pdu), count)

    @staticmethod
    def _decode_read(response: bytes, count: int) -> list[int]:
        if response[2] != count * 2:
            raise GboProtocolError(
                f"Unexpected byte count {response[2]}, expected {count * 2}"
            )
        data = response[3:3 + response[2]]
        return [(data[i] << 8) | data[i + 1] for i in range(0, len(data), 2)]

    async def write_multiple_registers(self, address: int, values: Sequence[int]) -> None:
        async with self._lock:
            await self.write_multiple_registers_unlocked(address, values)

    async def write_multiple_registers_unlocked(
        self, address: int, values: Sequence[int]
    ) -> None:
        values = [int(v) for v in values]
        if not values:
            raise ValueError("No values")
        if any(v < 0 or v > 0xFFFF for v in values):
            raise ValueError("Register value out of range")
        payload = b"".join(v.to_bytes(2, "big") for v in values)
        count = len(values)
        pdu = bytes((
            self.slave_id, 0x10,
            (address >> 8) & 0xFF, address & 0xFF,
            (count >> 8) & 0xFF, count & 0xFF,
            len(payload),
        )) + payload
        # FW 3.021 was captured returning vendor-specific 0x0055 in the FC16
        # echo field. Validate slave/function/CRC, but not the echoed count.
        await self._transaction_unlocked(pdu)
