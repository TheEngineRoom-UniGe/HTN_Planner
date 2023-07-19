#!/usr/bin/env python
import rospy
from std_msgs.msg import Int32
from geometry_msgs.msg import Pose
from sensor_msgs.msg import Image
from cv_bridge import CvBridge, CvBridgeError
# from handoverDetector import HandoverDetector
import cv2
import numpy as np
import tf
import quaternionic

class CameraListener():
    def __init__(self):
        rospy.init_node('camera_listener', anonymous=True)
        self.cv_b = CvBridge()
        
        self.marker_pose_pub = rospy.Publisher("/precise_marker_pose", Pose, queue_size=10)
        # self.handover_detector = HandoverDetector()
        # self.calibration_matrix_path = "/home/index1/index_ws/src/Baxter_Camera_Listener/scripts/zed2_calibration_matrix.npy"
        # self.calibration_matrix = np.load(self.calibration_matrix_path)    
        # self.distortion_path = "/home/index1/index_ws/src/Baxter_Camera_Listener/scripts/zed2_distortion.npy"
        # self.distortion = np.load(self.distortion_path)
        self.calibration_matrix = np.array([[359.64857211, 0.000e+00, 305.77728251],
                                            [0.000e+00, 363.0997639, 205.89834584],
                                            [0.000e+00, 0.000e+00, 1.000e+00]])
        self.distortion = np.array([0.11498325, -0.49102047, -0.00257414, -0.00573257,  0.52045801])
        self.saving_path = "./images/"
        self.image_id = 0
        self.tf_listener = tf.TransformListener()
        self.tf_w2cam = np.eye(4)
        self.current_marker = None
        self.enable_camera = False

    def get_transform_matrix(self, r_mat, t_vec):
        tf_mat = np.concatenate((r_mat, t_vec.reshape(3,1)), axis=1)
        tf_mat = np.concatenate((tf_mat, np.array([[0, 0, 0, 1]])), axis=0)
        return tf_mat
    
    def tf2quat_tr(self, tf):
        quat = quaternionic.array.from_rotation_matrix(tf[:3, :3])
        trasl = tf[:3, 3]
        return trasl, quat



    def estimatePoseSingleMarkers(self, corners, marker_size, mtx, distortion):
        '''
        This will estimate the rvec and tvec for each of the marker corners detected by:
        corners, ids, rejectedImgPoints = detector.detectMarkers(image)
        corners - is an array of detected corners for each detected marker in the image
        marker_size - is the size of the detected markers
        mtx - is the camera matrix
        distortion - is the camera distortion matrix
        RETURN list of rvecs, tvecs, and trash (so that it corresponds to the old estimatePoseSingleMarkers())
        '''

        

        marker_points = np.array([[-marker_size / 2, marker_size / 2, 0],
                                [marker_size / 2, marker_size / 2, 0],
                                [marker_size / 2, -marker_size / 2, 0],
                                [-marker_size / 2, -marker_size / 2, 0]], dtype=np.float32)
        trash = []
        rvecs = []
        tvecs = []
        i = 0
        for i in range(len(corners)):
            nada, R, t = cv2.solvePnP(marker_points, corners[i], mtx, distortion, False, cv2.SOLVEPNP_IPPE_SQUARE)
            rvecs.append(R)
            tvecs.append(t)
            trash.append(nada)
        return np.asarray(rvecs), np.asarray(tvecs), trash

    def aruco_display(self, corners, ids, rejected, image):
        if len(corners) > 0:
            # flatten the ArUco IDs list
            ids = ids.flatten()
            # loop over the detected ArUCo corners
            for (markerCorner, markerID) in zip(corners, ids):
                # extract the marker corners (which are always returned in
                # top-left, top-right, bottom-right, and bottom-left order)
                corners = markerCorner.reshape((4, 2))
                (topLeft, topRight, bottomRight, bottomLeft) = corners
                # convert each of the (x, y)-coordinate pairs to integers
                topRight = (int(topRight[0]), int(topRight[1]))
                bottomRight = (int(bottomRight[0]), int(bottomRight[1]))
                bottomLeft = (int(bottomLeft[0]), int(bottomLeft[1]))
                topLeft = (int(topLeft[0]), int(topLeft[1]))

                cv2.line(image, topLeft, topRight, (0, 255, 0), 2)
                cv2.line(image, topRight, bottomRight, (0, 255, 0), 2)
                cv2.line(image, bottomRight, bottomLeft, (0, 255, 0), 2)
                cv2.line(image, bottomLeft, topLeft, (0, 255, 0), 2)
                # compute and draw the center (x, y)-coordinates of the ArUco
                # marker
                cX = int((topLeft[0] + bottomRight[0]) / 2.0)
                cY = int((topLeft[1] + bottomRight[1]) / 2.0)
                cv2.circle(image, (cX, cY), 4, (0, 0, 255), -1)
                # draw the ArUco marker ID on the image
                cv2.putText(image, str(markerID),(topLeft[0], topLeft[1] - 10), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 255, 0), 2)
                print("[Inference] ArUco marker ID: {}".format(markerID))
                # show the output image
        return image


    def camera_callback(self, data):
        if not self.enable_camera:
            cv2.destroyAllWindows()
            return
        # rospy.loginfo(rospy.get_caller_id() + "I heard a message")
        try:
            cv_image = self.cv_b.imgmsg_to_cv2(data, desired_encoding="bgr8")
        except CvBridgeError as e:
            print(e)
        # cv_image = cv_image[0:380, 180:580]
        # cv_image = cv_image[0:360, :]
        # cv2.imshow("Image window",   cv_image)
        self.process(cv_image)

        # if self.image_id %20 == 0:

        #     print(self.saving_path + f'image_{self.image_id}.jpg')

        #     # cv2.imwrite(self.saving_path + f'image_{self.image_id}.jpg', cv_image)

        self.image_id += 1
        # self.handover_detector.find_orange_shape_and_compute_optical_flow(cv_image, height=cv_image.shape[0], width=cv_image.shape[1])
        cv2.waitKey(3)

    def listener(self, msg):
        self.enable_camera = True
        rospy.loginfo(f'Looking for this marker: {msg.data}')
        rospy.loginfo(f'Enabling camera: {self.enable_camera}')
        self.current_marker = msg.data
        # rospy.Subscriber("/cameras/right_hand_camera/image", Image, self.camera_callback)
        # rospy.loginfo("I am listening to the camera")

        # spin() simply keeps python from exiting until this node is stopped
        # rospy.spin()

    def process(self, image_ocv):

        static_rot = np.asarray([
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, -1.0]
        ])
        np.set_printoptions(formatter={'float': lambda x: "{0:0.3f}".format(x)})
        arucoDict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250) #cv2.aruco.DICT_ARUCO_ORIGINAL
        arucoParams = cv2.aruco.DetectorParameters()
        arucoDetector = cv2.aruco.ArucoDetector(arucoDict, arucoParams)


        image_ocv_grey = cv2.cvtColor(image_ocv, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = arucoDetector.detectMarkers(image_ocv_grey)


        rvec, tvec, _ = self.estimatePoseSingleMarkers(corners, 0.057, self.calibration_matrix, self.distortion)
        # rvec, tvec, _ = self.estimatePoseSingleMarkers(corners, 0.038, self.calibration_matrix, self.distortion)

        rod = [cv2.Rodrigues(r)[0] for r in rvec]
        ref_row = np.where(ids == self.current_marker)

        
        static_rot = np.asarray([
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, -1.0]
        ])

        if len(ref_row[0]) != 0:
            ref_row = ref_row[0][0]
            ref_rot = rod[ref_row]
            ref_rot = np.dot(ref_rot, static_rot)
            rvec[ref_row] = cv2.Rodrigues(ref_rot)[0]
            ref_trasl = tvec[ref_row]

            ref_tf = self.get_transform_matrix(ref_rot, ref_trasl)

            try:
                (trans,rot) = self.tf_listener.lookupTransform('/world', '/right_hand_camera', rospy.Time(0))
                q_rot = quaternionic.array([ rot[3], rot[0], rot[1], rot[2]])
                tf_w2cam = self.get_transform_matrix(q_rot.to_rotation_matrix, np.asarray(trans))
                # print(ref_tf)
                # print(tf_w2cam)
                # # print(np.dot(ref_tf,tf_w2cam))
                # print(self.tf2quat_tr(np.dot(tf_w2cam,ref_tf)))
                rt, rr = self.tf2quat_tr(np.dot(tf_w2cam,ref_tf))
                pose_msg = Pose()
                pose_msg.position.x = rt[0]
                pose_msg.position.y = rt[1]
                pose_msg.position.z = rt[2]
                pose_msg.orientation.x = rr.ndarray[0]
                pose_msg.orientation.y = rr.ndarray[1]
                pose_msg.orientation.z = rr.ndarray[2]
                pose_msg.orientation.w = rr.ndarray[3]

                br = tf.TransformBroadcaster()
                br.sendTransform(rt,
                          rr.ndarray,
                          rospy.Time.now(),
                          'marker' + str(self.current_marker),
                            'world')
                
                self.marker_pose_pub.publish(pose_msg)
                # rospy.logwarn(f'Published msg: {pose_msg}')
                self.enable_camera = False
                cv2.destroyAllWindows()
                return
            except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
                    print('')
        

        # if len(ref_row[0]) != 0:
        #     ref_row = ref_row[0][0]


        #     ref_rot = rod[ref_row]
        #     ref_rot = np.dot(ref_rot, static_rot)
        #     rvec[ref_row] = cv2.Rodrigues(ref_rot)[0]
        #     ref_trasl = tvec[ref_row]



        #     ref_tf = self.get_transform_matrix(ref_rot, ref_trasl)
        #     ref_tf = np.dot(tf_w2cam, ref_tf)
        #     print(ref_tf)
        #     np.save('/home/index1/index_ws/src/zed_cv2/bax2ref.npy', ref_tf)

        #     image_ocv = self.aruco_display(corners, ids, rejected, image_ocv)
        #     # # print(rvec.shape)
        #     # # print(tvec.shape)

        #     if tvec.shape[0] > 0 and rvec.shape[0] > 0:
        #         for j in range(tvec.shape[0]):
        #             cv2.drawFrameAxes(image_ocv, self.calibration_matrix, self.distortion, rvec[j], tvec[j], 0.05) 
                    
        #     image_resize = cv2.resize(image_ocv, (1280, 720))
        #     cv2.imshow("Image", image_resize)
        #     cv2.waitKey(1)


if __name__ == '__main__':
    camera_listener = CameraListener()
    image_sub = rospy.Subscriber("/baxter_camera_listener_activation", Int32, camera_listener.listener)
    rospy.Subscriber("/cameras/right_hand_camera/image", Image, camera_listener.camera_callback)
    # camera_listener.listener()
    rospy.spin()