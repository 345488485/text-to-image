export type AspectRatio='1:1'|'16:9'|'9:16';
export const aspectOptions: {label:string;value:AspectRatio}[]=[
 {label:'电脑宽屏 · 16:9 · 768 × 432',value:'16:9'},
 {label:'手机竖屏 · 9:16 · 432 × 768',value:'9:16'},
 {label:'正方形 · 1:1 · 512 × 512',value:'1:1'},
];
export function defaultAspect(width:number):AspectRatio {return width<700?'9:16':'16:9'}
export function inferAspect(job:{aspect_ratio?:string;width:number;height:number}):AspectRatio {
 if(job.aspect_ratio==='16:9'||job.aspect_ratio==='9:16'||job.aspect_ratio==='1:1')return job.aspect_ratio;
 return job.width>job.height?'16:9':job.width<job.height?'9:16':'1:1';
}
export function aspectDimensions(ratio:string):{width:number;height:number} {
 return ratio==='16:9'?{width:768,height:432}:ratio==='9:16'?{width:432,height:768}:{width:512,height:512};
}
