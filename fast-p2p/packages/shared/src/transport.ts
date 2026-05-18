export type TransportConnectionState = "connecting" | "online" | "offline"

export type TransportEventMap<TReceive> = {
  state: (state: TransportConnectionState) => void
  message: (message: TReceive) => void
  error: (error: Error) => void
}

export type TransportUnsubscribe = () => void

export interface ManagedTransport<TSend, TReceive> {
  readonly state: TransportConnectionState
  connect(): void
  disconnect(): void
  send(message: TSend): boolean
  on<TEvent extends keyof TransportEventMap<TReceive>>(
    event: TEvent,
    listener: TransportEventMap<TReceive>[TEvent],
  ): TransportUnsubscribe
}
