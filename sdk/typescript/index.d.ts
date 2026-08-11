export declare function version(): string
export declare function sandboxSupported(): boolean
export declare function compress(content: string): string
export declare function runtimeCheckPermission(policyJson: string, requiredJson: string): boolean
export declare function runtimeCheckCommand(cmd: string): boolean
export declare function runtimeSnapshot(workdir: string, snapshotDir: string, excludeJson?: string | undefined | null): number
export declare function runtimeRestore(workdir: string, snapshotDir: string): number
export declare function runtimeValidate(configsJson: string, edgesJson: string): boolean
export declare function runtimeCanRoute(configsJson: string, from: string, to: string): boolean
export declare function runtimeCredentialRewrite(routesJson: string, path: string): string | null
export declare function runtimeCredentialResolve(source: string): string
export declare class Runtime {
  constructor(configsJson: string, edgesJson: string)
  canRoute(from: string, to: string): boolean
  runOrder(entry?: string | undefined | null): Array<string>
  names(): Array<string>
}
