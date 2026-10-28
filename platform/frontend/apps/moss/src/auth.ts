import type {ApiClient,Session,User} from './api.ts';
export function canEnterWorkspace(user: Pick<User,'must_change_password'>|null): boolean {
  return !!user && !user.must_change_password;
}
export function passwordChangeError(current:string,next:string,confirm:string): string {
  if(!current) return '请输入当前密码。';
  if(next.length<10) return '新密码至少需要 10 个字符。';
  if(next===current) return '新密码不能与旧密码相同。';
  if(next!==confirm) return '两次输入的新密码不一致。';
  return '';
}
export async function changeOwnPassword(api:ApiClient,current:string,next:string,confirm:string):Promise<Session> {
  const error=passwordChangeError(current,next,confirm);
  if(error) throw new Error(error);
  return api.request<Session>('/auth/change-password',{method:'POST',body:{current_password:current,new_password:next}});
}
