import time
import math
import cv2
import os
import sys
import numpy as np
from ultralytics import YOLO

import VisionCaptureApi
import PX4MavCtrlV4 as PX4MavCtrl


class SmartUAVController:
    def __init__(self,
                 yolo_model_path="D:/RflySim/RflySimAPIs/我的实验/Car&Garbage/runs/train/yolov8n_faster_car_garbage2/weights/best.onnx",
                 copter_id=1):

        print("[系统初始化] 正在加载 YOLO 视觉大脑...")
        self.model = YOLO(yolo_model_path)

        print(f"[系统初始化] 正在连接 {copter_id} 号无人机...")
        self.mav = PX4MavCtrl.PX4MavCtrler(copter_id)

        # 设定出生点为原点 (0,0,0)
        self.mav.initPointMassModel(intAlt=0, intState=[0, 0, 0])
        time.sleep(1)  # 稍等一秒让引擎生成模型

        print("[系统初始化] 正在连接 3D 视觉引擎...")
        self.vis = VisionCaptureApi.VisionCaptureApi()
        self.vis.jsonLoad()
        isSuss = self.vis.sendReqToUE4()
        if not isSuss:
            print("【致命错误】连接 3D 引擎失败！请确认是直接双击打开的 RflySim3D.exe！")
            sys.exit(0)
        self.vis.startImgCap()
        time.sleep(1)

        self.save_dir = "UAV_Captures"
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)

        print("[系统初始化] 质点模式加载完美！无人机随时待命！")

    # 基础飞行控制模块 (质点模式极简版)
    def takeoff(self, altitude=10):
        """起飞到指定高度"""
        print(f"[飞行指令] 准备起飞至 {-altitude} (高度 {altitude} 米)...")
        self.mav.MaxSpeed = 5.0  # 设定起飞速度 5m/s
        self.mav.SendPosNED(0, 0, -altitude, 0)
        # 等待飞到目标高度
        time.sleep(altitude / 5.0 + 1)
        print("[飞行指令] 起飞完成，正在悬停。")

    def land(self):
        """原地降落"""
        print("[飞行指令] 开始降落...")
        self.mav.SendVelNED(0, 0, 1.5, 0)  # 1.5m/s 往下飞
        time.sleep(8)
        print("[飞行指令] 降落完毕。")

    def hover(self):
        """紧急悬停"""
        print("[飞行指令] 执行悬停...")
        self.mav.SendVelNED(0, 0, 0, 0)

    def fly_to(self, x, y, z, yaw):
        """飞往绝对坐标，并自动检测是否到达"""
        print(f"[飞行指令] 全速飞往目标: X={x}, Y={y}, 高度={-z}米")

        self.mav.MaxSpeed = 8.0  # 飞坐标时允许飞快一点
        self.mav.SendPosNED(x, y, z, yaw)
        time.sleep(20)


        print("[飞行指令] 已到达目标点。")

    def set_yaw(self, yaw_degree):
        """原地转向"""
        yaw_rad = math.radians(yaw_degree)
        pos = self.mav.uavPosNED
        self.mav.SendPosNED(pos[0], pos[1], pos[2], yaw_rad)
        time.sleep(2)
        print("[飞行指令] 转向完毕。")

    def move_forward(self, speed=2.0):
        print(f"[飞行指令] 正在以 {speed}m/s 的速度前进")
        self.mav.SendVelNED(speed, 0, 0, 0)

    def move_backward(self, speed=2.0):
        print(f"[飞行指令] 正在以 {speed}m/s 的速度后退")
        self.mav.SendVelNED(-speed, 0, 0, 0)

    def get_location(self):
        pos = self.mav.uavPosNED
        current_pos = (round(pos[0], 2), round(pos[1], 2), round(-pos[2], 2))
        return current_pos

# 高级复合任务模块：视觉巡逻闭环

    def patrol_and_search(self, target_name="car", speed=2.0, duration=120):
        print(f"[任务启动] 开始巡逻，寻找 {target_name}...")

        last_capture_pos = None
        found_count = 0
        start_time = time.time()

        # 启动前进速度
        self.mav.SendVelNED(speed, 0, 0, 0)

        while True:
            # 检查任务时间是否结束
            if time.time() - start_time >= duration:
                self.hover()
                print(f"\n[任务完成] {duration} 秒巡逻时间已到！")
                break

            # 视觉识别逻辑
            if self.vis.hasData[0]:
                img = self.vis.Img[0]
                results = self.model(img, conf=0.2, verbose=False)

                for r in results:
                    for box in r.boxes:
                        cls_id = int(box.cls[0].item())
                        detected_name = self.model.names[cls_id]

                        if detected_name.lower() == target_name.lower():
                            pos = self.get_location()

                            # 空间去重
                            if last_capture_pos is not None:
                                dist = math.sqrt((pos[0] - last_capture_pos[0]) ** 2 +
                                                 (pos[1] - last_capture_pos[1]) ** 2)
                                if dist < 8.0:
                                    continue

                            last_capture_pos = pos
                            found_count += 1

                            # 保存图片
                            timestamp = time.strftime("%H%M%S")
                            filename = f"{self.save_dir}/Found_{target_name}_{timestamp}.jpg"

                            # 标注并保存
                            annotated_img = results[0].plot()
                            cv2.imwrite(filename, annotated_img)

                            print(f"\n[发现目标] 发现 {target_name}!")
                            print(f"目标坐标(NED): X:{pos[0]:.2f}, Y:{pos[1]:.2f}, Z:{pos[2]:.2f}")
                            print(f"证据已保存: {filename}")

                            print("悬停1秒进行拍照取证...")
                            self.hover()
                            time.sleep(1.0)

                            print("悬停结束，继续巡逻...")
                            self.mav.SendVelNED(speed, 0, 0, 0)  # 重新给上速度
                            break

                # 画面渲染与显示
                annotated_img = results[0].plot()
                cv2.imshow("UAV AI Patrol Vision", annotated_img)
                self.vis.hasData[0] = False

            if cv2.waitKey(1) == 27:
                self.hover()
                break

            time.sleep(0.03)

        cv2.destroyAllWindows()
        return f"巡逻结束，共发现 {found_count} 个 {target_name}。"

    def __del__(self):
        """析构函数：程序退出时清理质点模式底层进程"""
        try:
            self.mav.EndPointMassModel()
        except:
            pass