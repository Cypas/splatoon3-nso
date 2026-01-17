import os, logging, mimetypes, re
from datetime import datetime
from typing import Optional, Union, Dict, Any, Tuple
from io import BytesIO

from nonebot import logger

from nonebot_plugin_splatoon3_nso import plugin_config

try:
    from qcloud_cos import CosConfig, CosS3Client
    from qcloud_cos.cos_exception import CosServiceError, CosClientError
except:
    CosConfig = CosS3Client = None
    CosServiceError = CosClientError = Exception


class COSUploader:
    def __init__(self):
        self.config = plugin_config.splatoon3_cos_config
        self.client = None
        if self.config.get('enabled', False) and all([CosConfig, CosS3Client]):
            self._init_client()

    def _init_client(self):
        try:
            cos_config = CosConfig(Region=self.config['region'], SecretId=self.config['secret_id'],
                                   SecretKey=self.config['secret_key'], Scheme='https')
            self.client = CosS3Client(cos_config)
            logger.info(f"[cos_uploader]cos_uploader初始化完成")
        except:
            pass

    def _validate_file(self, file_data: bytes, filename: str) -> bool:
        """图片大小校验"""
        return len(file_data) <= self.config.get('max_file_size', 100 * 1024 * 1024)

    def _generate_filename_with_dimensions(self, filename: str, width: int, height: int) -> str:
        """生成带尺寸的文件名"""
        name, ext = os.path.splitext(filename)
        return f"{name}_{width}x{height}{ext}"

    def _generate_cos_key(self, filename: str, custom_path: str = None, user_id: str = None,
                          dimensions: Tuple[int, int] = None) -> str:
        """生成上传凭证"""
        if dimensions and not self._has_dimensions_in_filename(filename):
            filename = self._generate_filename_with_dimensions(filename, dimensions[0], dimensions[1])
        if custom_path:
            custom_path = custom_path.replace('\\', '/')
            if '/' in custom_path:
                path_parts = custom_path.rsplit('/', 1)
                return f"{path_parts[0]}/{filename}"
            else:
                return filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        path_parts = [self.config.get('upload_path_prefix', 'mlog/')]
        if user_id:
            path_parts.append(f"{user_id}/")
        path_parts.append(f"{timestamp}/")
        return ''.join(path_parts) + filename.replace('\\', '/')

    def _has_dimensions_in_filename(self, filename: str) -> bool:
        return bool(re.search(r'_\d+x\d+\.[^.]+$', filename))

    def _get_content_type(self, filename: str) -> str:
        content_type, _ = mimetypes.guess_type(filename)
        return content_type or 'image/jpeg'

    def upload_file(self, file_data: Union[bytes, BytesIO], filename: str, user_id: str = None,
                    custom_path: str = None) -> Optional[Dict[str, Any]]:
        if not self.config.get('enabled', False) or not self.client:
            return None
        try:
            file_bytes = file_data.getvalue() if isinstance(file_data, BytesIO) else file_data
            if not self._validate_file(file_bytes, filename):
                return None
            dimensions_data = self._get_image_dimensions(file_bytes)
            dimensions = (dimensions_data['width'], dimensions_data['height']) if dimensions_data else (300, 300)
            cos_key = self._generate_cos_key(filename, custom_path, user_id, dimensions)
            response = self.client.put_object(Bucket=self.config['bucket_name'], Body=BytesIO(file_bytes),
                                              Key=cos_key, ContentType=self._get_content_type(filename))
            base_url = f"https://{self.config['domain']}" if self.config.get('domain') else \
                f"https://{self.config['bucket_name']}.cos.{self.config['region']}.myqcloud.com"
            return {
                'success': True, 'cos_key': cos_key, 'file_url': f"{base_url}/{cos_key}",
                'filename': os.path.basename(cos_key), 'file_size': len(file_bytes),
                'width': dimensions[0], 'height': dimensions[1], 'px': f'#{dimensions[0]}px #{dimensions[1]}px'
            }
        except:
            return None

    def delete_file(self, cos_key: str) -> bool:
        if not self.client:
            return False
        try:
            self.client.delete_object(Bucket=self.config['bucket_name'], Key=cos_key)
            return True
        except:
            return False

    def get_file_info(self, cos_key: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        try:
            response = self.client.head_object(Bucket=self.config['bucket_name'], Key=cos_key)
            return {'cos_key': cos_key, 'content_length': response.get('Content-Length'),
                    'content_type': response.get('Content-Type'), 'last_modified': response.get('Last-Modified')}
        except:
            return None

    def list_files(self, prefix: str = None, max_keys: int = 1000) -> Optional[list]:
        if not self.client:
            return None
        try:
            kwargs = {'Bucket': self.config['bucket_name'], 'MaxKeys': max_keys}
            if prefix:
                kwargs['Prefix'] = prefix
            response = self.client.list_objects(**kwargs)
            if 'Contents' not in response:
                return []
            return [{'key': obj['Key'], 'size': obj['Size'], 'last_modified': obj['LastModified']} for obj in
                    response['Contents']]
        except:
            return None


def parse_dimensions_from_filename(filename: str):
    match = re.search(r'_(\d+)x(\d+)\.[^.]+$', filename)
    return (int(match.group(1)), int(match.group(2))) if match else None


cos_uploader = COSUploader()


def upload_image(file_data: Union[bytes, BytesIO], filename: str, user_id: str = None,
                 custom_path: str = None, return_url_only: bool = False):
    result = cos_uploader.upload_file(file_data, filename, user_id, custom_path)
    return result['file_url'] if result and return_url_only else result


def upload_file(file_data: Union[bytes, BytesIO], filename: str, user_id: str = None, custom_path: str = None):
    return upload_image(file_data, filename, user_id, custom_path)


def simple_upload(file_data: Union[bytes, BytesIO], filename: str, upload_path: str = None,
                  return_url_only: bool = False):
    return upload_image(file_data, filename, custom_path=upload_path, return_url_only=return_url_only)


def _get_cos_base_url() -> str:
    base_url = f"https://{cos_uploader.config['domain']}" if cos_uploader.config.get('domain') else \
        f"https://{cos_uploader.config['bucket_name']}.cos.{cos_uploader.config['region']}.myqcloud.com"
    return base_url


def get_upload_url(cos_key: str):
    return f"{_get_cos_base_url()}/{cos_key}"


def delete_by_url(file_url: str):
    if not file_url:
        return False
    base_url = _get_cos_base_url()
    return cos_uploader.delete_file(file_url[len(base_url):]) if file_url.startswith(base_url) else False
