import time
import math
import cv2
import os
import sys
import threading
import requests
from ultralytics import YOLO

import VisionCaptureApi
import PX4MavCtrlV4 as PX4MavCtrl


class SwarmManager:
    def __init__(self, vehicle_num=3,yolo_model="D:/RflySim/RflySimAPIs/我的实验/Car&Garbage/runs/train/yolov8n_faster_car_garbage2/weights/best.onnx"):#换成你自己的地址，后续遇到同理
        self.vehicle_num = vehicle_num
        self.mav_list = []
        self.patrol_tasks = {i: None for i in range(1, vehicle_num + 1)}

        self.last_save_time = {i: 0 for i in range(1, vehicle_num + 1)}
        self.SAVE_COOLDOWN = 10.0  # 冷却时间：每 5 秒最多触发一次拍照和报警

        # 加入无人机“强制悬停”状态锁
        self.is_paused = {i: False for i in range(1, vehicle_num + 1)}

        print("[系统] 正在加载 YOLO 视觉大脑...")
        self.model = YOLO(yolo_model)

        print("[系统] 正在连接 3D 视觉引擎...")
        self.vis = VisionCaptureApi.VisionCaptureApi()
        self.vis.jsonLoad()
        if not self.vis.sendReqToUE4():
            print("【致命错误】连接 3D 引擎失败！")
            sys.exit(0)
        self.vis.startImgCap()
        time.sleep(1)

        print(f"[系统] 正在以【质点模式】初始化 {vehicle_num} 架无人机...")
        for i in range(vehicle_num):
            mav = PX4MavCtrl.PX4MavCtrler(i + 1)
            mav.initPointMassModel(intAlt=0, intState=[0, i * 5, 0])
            self.mav_list.append(mav)
        time.sleep(2)

        self.save_dir = "UAV_Captures"
        os.makedirs(self.save_dir, exist_ok=True)

        threading.Thread(target=self._telemetry_loop, daemon=True).start()
        threading.Thread(target=self._vision_loop, daemon=True).start()

        print("初始化完成！")
        self.last_infer_time = 0
        self.INFER_INTERVAL = 0.2  # 每0.2秒推理一次（≈5FPS）

        self.last_annotated_img = None
        self.last_infer_time = 0
        self.INFER_INTERVAL = 0.15  # 0.15秒 ≈ 6~7 FPS
        self.last_results = None  # 缓存检测结果
        self.last_detect_time = 0
        self.DETECT_COOLDOWN = 10.0


# 遥测与视觉后台线程
    def _telemetry_loop(self):
        """实时发送位置到网页大屏"""
        while True:
            for i, mav in enumerate(self.mav_list):
                pos = mav.uavPosNED
                payload = {"uav_id": f"UAV-{i + 1}", "x": pos[0], "y": pos[1], "z": pos[2]}
                try:
                    requests.post("http://127.0.0.1:5000/api/update", json=payload, timeout=0.1)
                except:
                    pass
            time.sleep(0.5)

    def _vision_loop(self):
        while True:
            try:
                if len(self.vis.hasData) > 0 and self.vis.hasData[0]:

                    img = self.vis.Img[0]
                    target_name = self.patrol_tasks[1]
                    current_time = time.time()

                    if target_name and (current_time - self.last_infer_time > self.INFER_INTERVAL):
                        self.last_results = self.model(img, conf=0.3, verbose=False)
                        self.last_infer_time = current_time

                    if self.last_results:
                        annotated_img = self.last_results[0].plot()
                        results = self.last_results
                    else:
                        annotated_img = img
                        results = []


                    # 位置的检测逻辑
                    if target_name and results:
                        for r in results:
                            for box in r.boxes:
                                cls_name = self.model.names[int(box.cls[0].item())].lower()

                                if cls_name == target_name.lower():


                                    if current_time - self.last_detect_time < self.DETECT_COOLDOWN:
                                        continue

                                    self.last_detect_time = current_time

                                    pos = self.mav_list[0].uavPosNED

                                    print(f"\n检测到目标！X:{pos[0]:.2f}, Y:{pos[1]:.2f}, Z:{pos[2]:.2f}")

                                    timestamp = time.strftime('%H%M%S')
                                    filename = f"{self.save_dir}/UAV1_{target_name}_{timestamp}.jpg"

                                    threading.Thread(
                                        target=self._save_and_upload,
                                        args=(filename, annotated_img.copy(), pos, target_name),
                                        daemon=True
                                    ).start()

                                    self.is_paused[1] = True
                                    self.mav_list[0].SendVelNED(0, 0, 0, 0)
                                    time.sleep(2)
                                    self.is_paused[1] = False

                                    break
                            else:
                                continue
                            break


                    # 画面显示

                    small_img = cv2.resize(annotated_img, (800, 450))
                    status_text = f"UAV-1 Vision (Target: {target_name})" if target_name else "UAV-1 Vision (Standby)"
                    cv2.putText(small_img, status_text, (15, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

                    cv2.imshow("Single Drone AI Patrol", small_img)

                    self.vis.hasData[0] = False

                cv2.waitKey(1)
                time.sleep(0.01)

            except Exception as e:
                print("Vision线程异常:", e)
                time.sleep(0.5)

    def _save_and_upload(self, filename, img, pos, target_name):
        try:
            cv2.imwrite(filename, img)
            print(f"已保存: {filename}")

            # 上传图片并获取服务器返回的 img_url
            img_url = ""
            with open(filename, 'rb') as f:
                files = [('image', (os.path.basename(filename), f, 'image/jpeg'))]
                data = {
                    "uav_id": "UAV-1",
                    "target": target_name,
                }
                res = requests.post(
                    "http://127.0.0.1:5000/api/upload_evidence",
                    data=data,
                    files=files,
                    timeout=2.0
                )
                if res.status_code == 200:
                    print("上传成功")
                    img_url = res.json().get("img_url", "")  # 获取后端返回的URL
                else:
                    print(f"上传失败: {res.status_code}")
                    return

            # 发送地图标记（带图片URL）
            marker_payload = {
                "uav_id": "UAV-1",
                "target": target_name,
                "x": round(pos[0], 2),
                "y": round(pos[1], 2),
                "z": round(pos[2], 2),
                "img_url": img_url
            }
            marker_res = requests.post(
                "http://127.0.0.1:5000/api/add_marker",
                json=marker_payload,
                timeout=1.0
            )
            if marker_res.status_code == 200:
                print("📍 地图标记已发送")
            else:
                print("⚠️ 标记发送失败")

        except Exception as e:
            print("⚠️ IO线程错误:", e)

#平滑航点飞行 (加入断点续飞功能)
    def _smooth_fly_to(self, copter_id, x, y, z, yaw_rad, speed):
        mav = self.mav_list[copter_id - 1]
        mav.MaxSpeed = speed
        mav.SendPosNED(x, y, z, yaw_rad)

        was_paused = False
        while True:
            if self.is_paused[copter_id]:
                was_paused = True
                time.sleep(0.5)
                continue

            if was_paused:
                mav.SendPosNED(x, y, z, yaw_rad)
                was_paused = False

            pos = mav.uavPosNED
            dist = math.sqrt((x - pos[0]) ** 2 + (y - pos[1]) ** 2)
            if dist < 2.0:
                break
            time.sleep(0.2)

    def prepare_all(self):
        print("[全局指令] 前往巡逻起始点就位...")

        self.mav_list[0].MaxSpeed = 8.0
        self.mav_list[0].SendPosNED(-350, -50, -20, 0)

        self.mav_list[1].MaxSpeed = 8.0
        self.mav_list[1].SendPosNED(-350, -32, -20, 0)

        self.mav_list[2].MaxSpeed = 8.0
        self.mav_list[2].SendPosNED(-350, -20, -20, 0)

        time.sleep(15)
        print("[全局指令] 所有无人机就位完毕！等待巡逻指令。")

    def hover(self, copter_id):
        self.mav_list[copter_id - 1].SendVelNED(0, 0, 0, 0)


#任务一
    def async_patrol_left(self, copter_id, target_name=None, speed=2.0):
        def _task():
            self.patrol_tasks[copter_id] = target_name
            self._smooth_fly_to(copter_id, 10, -50, -20, 0, speed)
            self.mav_list[copter_id - 1].SendPosNED(10, -50, -20, -1.5708);
            time.sleep(4)
            self._smooth_fly_to(copter_id, 10, -300, -20, -1.5708, speed)
            self.patrol_tasks[copter_id] = None
            self.hover(copter_id)

        threading.Thread(target=_task, daemon=True).start()

# 任务二
    def async_patrol_straight(self, copter_id, target_name=None, speed=2.0):
        def _task():
            self.patrol_tasks[copter_id] = target_name
            self._smooth_fly_to(copter_id, 350, -32, -20, 0, speed)
            self.patrol_tasks[copter_id] = None
            self.hover(copter_id)

        threading.Thread(target=_task, daemon=True).start()

# 任务三
    def async_patrol_right(self, copter_id, target_name=None, speed=2.0):
        def _task():
            self.patrol_tasks[copter_id] = target_name
            self._smooth_fly_to(copter_id, -5, -20, -20, 0, speed)
            self.mav_list[copter_id - 1].SendPosNED(-5, -20, -20, 1.5708);
            time.sleep(4)
            self._smooth_fly_to(copter_id, -5, 300, -20, 1.5708, speed)
            self.patrol_tasks[copter_id] = None
            self.hover(copter_id)

        threading.Thread(target=_task, daemon=True).start()


    def run_single_vision_mission(self, target_name="garbage"):
        """模式一：单机 AI 视觉巡逻"""
        print(f"\n[模式一] 启动单机 AI 视觉巡逻，目标：{target_name}！")
        # 1. 飞向起点 (-350)
        self.mav_list[0].MaxSpeed = 8.0
        self.mav_list[0].SendPosNED(-350, -32, -20, 0)
        time.sleep(15)
        # 2. 开启直行巡逻
        self.async_patrol_straight(copter_id=1, target_name=target_name, speed=3.0)

    def run_swarm_blind_mission(self):
        """模式二：三机集群盲飞协同"""
        print("\n[模式二] 启动三机协同集群拉网巡逻！")
        self.mav_list[0].MaxSpeed = 8.0;
        self.mav_list[0].SendPosNED(-350, -50, -20, 0)
        self.mav_list[1].MaxSpeed = 8.0;
        self.mav_list[1].SendPosNED(-350, -32, -20, 0)
        self.mav_list[2].MaxSpeed = 8.0;
        self.mav_list[2].SendPosNED(-350, -20, -20, 0)
        time.sleep(15)
        self.async_patrol_left(copter_id=1, target_name=None, speed=3.0)
        self.async_patrol_straight(copter_id=2, target_name=None, speed=3.0)
        self.async_patrol_right(copter_id=3, target_name=None, speed=3.0)

    def land_all(self):
        print("\n[全局指令] 收到返回指令，全部开始降落！")
        for mav in self.mav_list:
            mav.SendVelNED(0, 0, 1.0, 0)