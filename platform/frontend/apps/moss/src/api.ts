export interface User { id: string; username: string; role: 'admin' | 'user'; must_change_password: boolean; is_active?: boolean; created_at?: string }
export interface Session { user: User; csrf_token: string }
export interface Job { id: string; prompt: string; negative_prompt: string; steps: number; seed: number; status: 'queued'|'running'|'succeeded'|'failed'|'cancelled'; created_at: string; started_at: string|null; finished_at: string|null; error: string|null; queue_position: number|null; image_url: string|null; width: number; height: number; aspect_ratio?: string }
export interface JobList { items: Job[]; total: number; page: number; page_size: number }
export interface EngineStatus { engine_online: boolean; worker_online?: boolean; queue_length: number; running: boolean; model: string }
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {super(message);this.status=status;}
}
export class ApiClient {
  csrfToken = '';
  private fetcher: typeof fetch;
  private expired: () => void;
  constructor(fetcher: typeof fetch = fetch, expired: () => void = () => {}) { this.fetcher=fetcher.bind(globalThis);this.expired=expired; }
  async request<T>(path: string, options: {method?: string;body?: unknown} = {}): Promise<T> {
    if (!/^\/[a-z]/.test(path) || path.includes('://')) throw new Error('无效API路径');
    const method = options.method ?? 'GET';
    let response: Response;
    try {
      response=await this.fetcher(`/api${path}`, {method,credentials:'same-origin',headers:{'Content-Type':'application/json',...(method !== 'GET' ? {'X-CSRF-Token':this.csrfToken} : {})},...(options.body === undefined ? {} : {body:JSON.stringify(options.body)})});
    } catch {throw new Error('无法连接平台服务，请检查后端是否已启动。');}
    if (response.status===401) {this.csrfToken='';this.expired();}
    const data=await response.json().catch(()=>({}));
    if (!response.ok) throw new ApiError(typeof data.detail==='string' ? data.detail : `请求失败（${response.status}），请检查输入后重试。`, response.status);
    if (data.csrf_token) this.csrfToken=data.csrf_token;
    return data as T;
  }
}
