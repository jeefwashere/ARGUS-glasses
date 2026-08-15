/// <reference types="vite/client" />

declare module "*.glb?url" {
  const src: string;
  export default src;
}
