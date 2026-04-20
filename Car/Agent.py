import os
import re
import time
from openai import OpenAI
from SmartUAV import SmartUAVController
import speech_recognition as sr

ARK_API_KEY = ""
MODEL_NAME = ""

client = OpenAI(
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    api_key=ARK_API_KEY,
)

# 设定系统提示词 (Prompt)

SYS_MSG = """
你是一个智慧城市低空巡逻指挥官。任务是将人类的自然语言指令转化为极简的 Python 代码，控制一架名为 `uav` 的无人机。

【严格规则】
1. 运行环境中已实例化无人机控制器对象，名为 `uav`（类型为 SmartUAVController）。
2. 绝对禁止输出任何 import 语句，禁止输出任何多线程或循环逻辑！所有指令均为一次性调用，底层已实现异步或阻塞等待。
3. 只能使用下面列出的可用指令，直接调用即可。
4. 回复必须且只包含一个 Markdown 代码块。

【可用指令库】
uav.takeoff(altitude)                # 起飞到指定高度(米)，阻塞直到完成
uav.land()                           # 原地降落，阻塞直到完成
uav.hover()                          # 紧急悬停（立即停止运动）
uav.move_forward(speed=2.0)          # 以给定速度(米/秒)向前直线飞行（不会自动停止，需配合其他指令）
uav.move_backward(speed=2.0)         # 以给定速度(米/秒)向后直线飞行
uav.fly_to(x, y, z,yao)              # 飞往绝对坐标(x,y,z)，z为负表示高度（如-10为10米高），阻塞直到接近目标.默认任务开始位置就是（-92, 148, -5, 0）
uav.set_yaw(degree)                  # 原地转向到指定角度（0~360度），阻塞完成
uav.get_location()                   # 获取当前坐标，返回元组(x, y, z)，仅用于查询，不产生运动
uav.patrol_and_search(target_name, speed=2.0)  # 执行视觉巡逻任务，持续向前飞行并搜索目标（target_name如"car","garbage"），不特意说，目标就是车，按ESC键退出，阻塞运行
uav.preparationP()                    #当用户说前往任务开始地点，或类似表达，就执行这个函数
【输出范例】
用户："起飞到5米，然后向前飞3米每秒"
```python
uav.takeoff(5)

用户："前往任务开始地点"
```python
uav.fly_to(-92, 148, -5, 0)

用户："开始执行任务，巡逻搜索违停车辆，速度2.5"
uav.patrol_and_search("car", 2.5)

"""

chat_history =[{"role": "system", "content": SYS_MSG}]



# 新增：语音转文字模块
def listen_command():
    recognizer = sr.Recognizer()

    # 音量门槛（值越小越敏感，默认是300）
    recognizer.energy_threshold = 300
    # 彻底关闭动态适应
    recognizer.dynamic_energy_threshold = False
    # 停顿时间

    recognizer.pause_threshold = 0.5

    with sr.Microphone() as source:
        print("\n[系统录音] 麦克风已就绪...")

        print("[系统录音] 请开始说话 (允许短暂停顿，说完后请保持安静 1.5 秒)...")

        try:
            # phrase_time_limit
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
            print("[系统录音] 录音结束，正在云端识别中...")

            # 调用识别
            text = recognizer.recognize_google(audio, language='zh-CN')
            print(f"[语音识别成功] 你说的是: '{text}'")
            return text

        except sr.WaitTimeoutError:
            print("⚠️ [语音识别] 等待超时，未检测到声音。")
            return ""
        except sr.UnknownValueError:
            print("⚠️ [语音识别] 未能听清您说的话，请再说一遍。")
            return ""
        except sr.RequestError as e:
            print(f"❌ [语音识别] 语音服务请求失败！错误信息: {e}")
            return ""

def chat(prompt, history):
    history.append({"role": "user", "content": prompt})
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=history,
        temperature=0.1,  # 设定低温度以保证生成代码的严谨性和稳定性
    )

    content = completion.choices[0].message.content
    history.append({"role": "assistant", "content": content})

    return content


#使用正则表达式精确提取 Markdown 中的 python 代码
def extract_python_code(content):

    match = re.search(r'python\n(.*?)\n', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""

if __name__ == "__main__":
    print("正在启动 RflySim 大模型智能体系统...")

    uav = SmartUAVController(yolo_model_path="D:/RflySim/RflySimAPIs/我的实验/Car&Garbage/runs/train/yolov8n_faster_car_garbage2/weights/best.onnx")

    print("\n系统启动完毕！请输入指令 (输入 'q' 退出)。")
    print("你可以选择【打字输入】或【语音输入】下达指令。")

    while True:
        # 提供双模态选择
        print("\n" + "-" * 40)
        print("请选择输入方式：")
        print("语音输入 (按回车键开始录音)")
        print("打字输入 (直接输入指令)")
        print("退出系统 (输入 'q')")

        user_input = input("\n你的选择 (直接输入文字，或按回车录音): ")

        user_cmd = ""

        if user_input.lower() == 'q':
            print("正在退出系统，执行安全降落...")
            uav.land()
            break
        elif user_input == "":
            # 用户直接按了回车，进入语音模式
            user_cmd = listen_command()
            if not user_cmd:
                continue  # 识别失败，重新循环
        else:
            user_cmd = user_input

        print("正在翻译指令为代码...")
        reply = chat(user_cmd, chat_history)

        # 提取生成的 Python 代码
        code = extract_python_code(reply)

        if code:
            print("\n========== 提取到的代码 ==========")
            print(code)
            print("==================================\n")

            print("正在执行代码...")
            try:
                exec(code)
            except Exception as e:
                print(f"代码执行异常: {e}")
        else:
            print("\n未能提取到标准 Python 代码，大模型原始回复如下：")
            print(reply)