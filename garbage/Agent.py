import os
import re
import time
import speech_recognition as sr
from openai import OpenAI
from SwarmCore import SwarmManager

ARK_API_KEY = ""
MODEL_NAME = ""

client = OpenAI(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key=ARK_API_KEY,
)



SYS_MSG = """
你是一个高级智慧城市低空巡逻指挥官。任务是将人类的自然语言指令转化为 Python 代码。

【严格规则】
1. 运行环境中已实例化集群控制器对象 `swarm`。
2. 绝对禁止输出 import 语句，禁止输出多线程或循环逻辑！
3. 回复必须且只包含一个 Markdown 代码块，不要废话。

【你拥有的四个终极指令】
# 1. 启动【单机视觉模式】：派1号机单飞，并开启摄像头找目标。
swarm.run_single_vision_mission(target_name)  # 例: swarm.run_single_vision_mission('garbage')

# 2. 启动【三机群飞模式】：派3架飞机同时拉网巡逻（无摄像头）。
swarm.run_swarm_blind_mission()

# 3. 全军降落
swarm.land_all()

# 4. 全体无人机就为（群体巡逻前准备）
prepare_all(self)

【输出范例】
用户："执行单机视觉巡逻，帮我找一下垃圾"
```python
swarm.run_single_vision_mission('garbage')
【输出范例】
用户：“全体起飞，就位”
```python
swarm.prepare_all()
"""



chat_history = [{"role": "system", "content": SYS_MSG}]



def listen_command():
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = False
    recognizer.pause_threshold = 0.5
    with sr.Microphone() as source:
        print("\n[系统录音] 麦克风已就绪...")
        print("请开始说话 (说完后请保持安静 0.5 秒)...")

        try:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
            print("[系统录音] 录音结束，正在云端识别中...")
            text = recognizer.recognize_google(audio, language='zh-CN')
            print(f"[语音识别成功] 你说的是: '{text}'")
            return text
        except sr.WaitTimeoutError:
            print("[语音识别] 等待超时，未检测到声音。")
            return ""
        except sr.UnknownValueError:
            print("[语音识别] 未能听清您说的话，请再说一遍。")
            return ""
        except sr.RequestError as e:
            print(f"[语音识别] 语音服务请求失败！错误信息: {e}")
            return ""

def chat(prompt, history):
    history.append({"role": "user", "content": prompt})
    completion = client.chat.completions.create(
    model=MODEL_NAME,
    messages=history,
    temperature=0.1,
    )
    content = completion.choices[0].message.content
    history.append({"role": "assistant", "content": content})
    return content



def extract_python_code(content):
    match = re.search(r'python\n(.*?)\n', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""



if __name__ == "__main__":
    print("正在启动 RflySim 多机协同 Agent 指挥部...")
    swarm = SwarmManager(vehicle_num=3)

    print("\n部署完毕！")

    while True:
        print("\n" + "-" * 40)
        print("请选择输入方式：")
        print("语音输入 (直接按回车键开始录音)")
        print("打字输入 (直接输入文字指令)")
        print("退出系统 (输入 'q')")

        user_input = input("\n请输入: ")

        user_cmd = ""
        if user_input.lower() == 'q':
            print("正在退出系统，全舰队执行安全降落...")
            swarm.land_all()
            break
        elif user_input == "":
            user_cmd = listen_command()
            if not user_cmd:
                continue
        else:
            user_cmd = user_input

        print("\n正在翻译指令...")
        reply = chat(user_cmd, chat_history)

        code = extract_python_code(reply)

        if code:
            print("\n========== 翻译代码 ============")
            print(code)
            print("============================================\n")

            print("正在执行指令...")
            try:
                exec(code)
            except Exception as e:
                print(f"代码执行异常: {e}")
        else:
            print("\n未能提取到标准 Python 代码，大模型原始回复如下：")
            print(reply)