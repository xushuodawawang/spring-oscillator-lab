// 在独立文档中复用已验证的教学页面；高度随结果变化，整页统一滚动。
export default function(component) {
    const { parentElement, data } = component;
    const host = parentElement.querySelector('#lab-host');
    const frame = document.createElement('iframe');
    frame.id = 'spring-lab-frame';
    frame.title = '弹簧振子实验分析';
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-downloads allow-modals');
    frame.style.height = '560px';
    let observer = null;
    frame.onload = () => {
        if (observer) observer.disconnect();
        const body = frame.contentDocument.body;
        const resize = () => {
            const height = Math.max(400, Math.ceil(body.getBoundingClientRect().height) + 2);
            if (frame.style.height !== height + 'px') frame.style.height = height + 'px';
        };
        observer = new ResizeObserver(resize);
        observer.observe(body);
        resize();
    };
    // data.page 是仓库内生成的固定HTML，不包含用户图片或用户输入的HTML。
    frame.srcdoc = data.page;
    host.appendChild(frame);
    return () => {
        if (observer) observer.disconnect();
        frame.onload = null;
        frame.remove();
    };
}
