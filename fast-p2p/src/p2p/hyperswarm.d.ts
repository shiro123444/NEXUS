declare module "hyperswarm" {
  import { EventEmitter } from "events"

  interface HyperswarmOptions {
    keyPair?: any
    seed?: Buffer
    maxPeers?: number
    firewall?: (remotePublicKey: Buffer) => boolean
  }

  interface PeerInfo {
    publicKey: Buffer
    topics: Buffer[]
  }

  interface Discovery {
    flushed(): Promise<void>
    destroy(): Promise<void>
  }

  class Hyperswarm extends EventEmitter {
    constructor(opts?: HyperswarmOptions)
    join(topic: Buffer, opts?: { server?: boolean; client?: boolean }): Discovery
    leave(topic: Buffer): Promise<void>
    destroy(): Promise<void>
    on(event: "connection", listener: (conn: any, info: PeerInfo) => void): this
  }

  export default Hyperswarm
}
