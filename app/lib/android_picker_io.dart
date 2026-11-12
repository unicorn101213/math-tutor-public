import 'package:image_picker_android/image_picker_android.dart';
import 'package:image_picker_platform_interface/image_picker_platform_interface.dart';

void enableAndroidPhotoPicker() {
  if (ImagePickerPlatform.instance is ImagePickerAndroid) {
    (ImagePickerPlatform.instance as ImagePickerAndroid).useAndroidPhotoPicker = true;
  }
}
